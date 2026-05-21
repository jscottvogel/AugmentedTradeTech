import os
import logging
import base64
from datetime import datetime, timezone, timedelta
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.app.models.company import Company
from apps.api.app.models.invoice import Invoice
from apps.api.app.models.customer import Customer

logger = logging.getLogger("qbo_sync")

class QBOClient:
    def __init__(self, db: Session, company_id: str):
        self.db = db
        self.company_id = company_id
        
        self.company = db.scalar(
            select(Company).where(Company.id == company_id)
        )
        if not self.company:
            raise ValueError(f"Company {company_id} not found")
            
        self.client_id = os.getenv("QBO_CLIENT_ID")
        self.client_secret = os.getenv("QBO_CLIENT_SECRET")
        self.redirect_uri = os.getenv("QBO_REDIRECT_URI", "http://localhost:8000/integrations/qbo/callback")
        
        # Fall back to mock mode if realm_id starts with mock_ or client ID/secret are not configured
        self.is_mock = (
            (self.company.qbo_realm_id and self.company.qbo_realm_id.startswith("mock_")) or
            not self.client_id or
            not self.client_secret
        )
        if self.is_mock:
            logger.info(f"QBOClient initialized in MOCK mode for company {company_id}")

    def get_auth_url(self, state: str) -> str:
        if self.is_mock:
            # Redirect back to the local callback with mock parameters
            frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
            return f"{frontend_url}/settings/integrations?mock_callback=true&code=mock_code_123&realmId=mock_realm_abc&state={state}"
            
        # QuickBooks Auth endpoint
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "scope": "com.intuit.quickbooks.accounting",
            "redirect_uri": self.redirect_uri,
            "state": state
        }
        url_params = "&".join(f"{k}={v}" for k, v in params.items())
        return f"https://appcenter.intuit.com/connect/oauth2?{url_params}"

    def exchange_code(self, code: str) -> dict:
        if self.is_mock or code.startswith("mock_"):
            return {
                "access_token": "mock_access_token_xyz",
                "refresh_token": "mock_refresh_token_123",
                "realm_id": self.company.qbo_realm_id or "mock_realm_abc",
                "expires_in": 3600
            }
            
        auth_str = f"{self.client_id}:{self.client_secret}"
        auth_b64 = base64.b64encode(auth_str.encode()).decode()
        
        headers = {
            "Authorization": f"Basic {auth_b64}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        }
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri
        }
        
        response = httpx.post("https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer", headers=headers, data=data)
        if response.status_code != 200:
            raise ValueError(f"Failed to exchange authorization code: {response.text}")
            
        return response.json()

    def refresh_token_if_needed(self):
        if self.is_mock:
            # Automatically extend expiration time in mock mode
            if not self.company.qbo_token_expires_at or self.company.qbo_token_expires_at < datetime.now(timezone.utc):
                self.company.qbo_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
                self.db.add(self.company)
                self.db.flush()
            return
            
        if not self.company.qbo_refresh_token:
            raise ValueError("No refresh token available to refresh")
            
        now = datetime.now(timezone.utc)
        # Refresh if token expires in less than 1 hour, or is already expired
        if not self.company.qbo_token_expires_at or (self.company.qbo_token_expires_at - now < timedelta(hours=1)):
            logger.info(f"Refreshing QBO OAuth token for company {self.company_id}")
            
            auth_str = f"{self.client_id}:{self.client_secret}"
            auth_b64 = base64.b64encode(auth_str.encode()).decode()
            
            headers = {
                "Authorization": f"Basic {auth_b64}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json"
            }
            data = {
                "grant_type": "refresh_token",
                "refresh_token": self.company.qbo_refresh_token
            }
            
            response = httpx.post("https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer", headers=headers, data=data)
            if response.status_code != 200:
                logger.error(f"Failed to refresh QBO token: {response.text}")
                # Clear invalid tokens
                self.company.qbo_access_token = None
                self.company.qbo_refresh_token = None
                self.company.qbo_token_expires_at = None
                self.company.qbo_realm_id = None
                self.db.add(self.company)
                self.db.flush()
                raise ValueError("QuickBooks Online credentials expired or invalid. Please reconnect.")
                
            token_data = response.json()
            self.company.qbo_access_token = token_data["access_token"]
            self.company.qbo_refresh_token = token_data.get("refresh_token", self.company.qbo_refresh_token)
            expires_in = token_data.get("expires_in", 3600)
            self.company.qbo_token_expires_at = now + timedelta(seconds=expires_in)
            self.db.add(self.company)
            self.db.flush()

    def get_or_create_customer(self, customer: Customer) -> str:
        if self.is_mock:
            return f"mock_qbo_cust_{customer.id}"
            
        # 1. Match by Email
        if customer.email:
            query = f"SELECT * FROM Customer WHERE PrimaryEmailAddr = '{customer.email}'"
            res = self._api_request("GET", f"query?query={query}")
            customers = res.get("QueryResponse", {}).get("Customer", [])
            if customers:
                return customers[0]["Id"]
                
        # 2. Match by Phone
        if customer.phone:
            query = f"SELECT * FROM Customer WHERE PrimaryPhone = '{customer.phone}'"
            res = self._api_request("GET", f"query?query={query}")
            customers = res.get("QueryResponse", {}).get("Customer", [])
            if customers:
                return customers[0]["Id"]

        # 3. Match by Display Name
        display_name = f"{customer.first_name} {customer.last_name}".strip()
        if not display_name:
            display_name = customer.email or "Unnamed Customer"
            
        escaped_name = display_name.replace("'", "\\'")
        query = f"SELECT * FROM Customer WHERE DisplayName = '{escaped_name}'"
        res = self._api_request("GET", f"query?query={query}")
        customers = res.get("QueryResponse", {}).get("Customer", [])
        if customers:
            return customers[0]["Id"]

        # 4. Create new customer in QBO
        customer_payload = {
            "GivenName": customer.first_name or "",
            "FamilyName": customer.last_name or "",
            "DisplayName": display_name,
            "PrimaryEmailAddr": {"Address": customer.email or ""},
            "PrimaryPhone": {"FreeFormNumber": customer.phone or ""},
            "BillAddr": {
                "Line1": customer.address_line1 or "",
                "Line2": customer.address_line2 or "",
                "City": customer.city or "",
                "CountrySubDivisionCode": customer.state or "",
                "PostalCode": customer.zip or ""
            }
        }
        
        try:
            create_res = self._api_request("POST", "customer", json_data=customer_payload)
            return create_res["Customer"]["Id"]
        except Exception as err:
            # Handle DisplayName collision
            if "already exists" in str(err).lower() or "duplicate" in str(err).lower():
                customer_payload["DisplayName"] = f"{display_name} ({customer.id[-4:]})"
                create_res = self._api_request("POST", "customer", json_data=customer_payload)
                return create_res["Customer"]["Id"]
            raise err

    def _get_revenue_account_id(self) -> str:
        if self.is_mock:
            return "mock_acc_1"
            
        # Search for a standard Revenue/Income Account
        query = "SELECT * FROM Account WHERE AccountType = 'Revenue' or AccountType = 'Income'"
        res = self._api_request("GET", f"query?query={query}")
        accounts = res.get("QueryResponse", {}).get("Account", [])
        if accounts:
            return accounts[0]["Id"]
            
        # Fallback to Sales accounts
        query = "SELECT * FROM Account WHERE Name LIKE '%Sales%'"
        res = self._api_request("GET", f"query?query={query}")
        accounts = res.get("QueryResponse", {}).get("Account", [])
        if accounts:
            return accounts[0]["Id"]
            
        raise ValueError("Could not resolve any active Revenue or Income account in QuickBooks chart of accounts.")

    def get_or_create_item(self, line_type: str, description: str) -> str:
        if self.is_mock:
            return f"mock_qbo_item_{line_type}"
            
        mappings = self.company.qbo_item_mappings or {}
        
        if line_type == "labor":
            item_name = mappings.get("labor", "Labor")
            is_service = True
        elif line_type == "fee":
            item_name = mappings.get("fee", "Fee")
            is_service = True
        else: # part
            # Part name resolved from description
            item_name = description.replace(":", " ").strip()
            if len(item_name) > 100:
                item_name = item_name[:97] + "..."
            if not item_name:
                item_name = mappings.get("part_fallback", "Parts")
            is_service = False

        # 1. Search for existing item
        escaped_name = item_name.replace("'", "\\'")
        query = f"SELECT * FROM Item WHERE Name = '{escaped_name}'"
        res = self._api_request("GET", f"query?query={query}")
        items = res.get("QueryResponse", {}).get("Item", [])
        if items:
            return items[0]["Id"]
            
        # 2. Create Item if not found
        income_account_id = self._get_revenue_account_id()
        item_payload = {
            "Name": item_name,
            "Type": "Service" if is_service else "NonInventory",
            "IncomeAccountRef": {
                "value": income_account_id
            }
        }
        
        try:
            create_res = self._api_request("POST", "item", json_data=item_payload)
            return create_res["Item"]["Id"]
        except Exception as err:
            # If creating description-specific part item fails, fallback to Parts general item
            if line_type == "part" and item_name != mappings.get("part_fallback", "Parts"):
                fallback_name = mappings.get("part_fallback", "Parts")
                return self.get_or_create_item("part_fallback", fallback_name)
            raise err

    def create_invoice(self, invoice: Invoice, qbo_customer_id: str) -> str:
        if self.is_mock:
            return f"mock_qbo_inv_{invoice.id}"
            
        lines = []
        for item in invoice.line_items:
            qbo_item_id = self.get_or_create_item(item.line_type, item.description)
            amount_dollars = float(item.total_cents) / 100.0
            unit_price_dollars = float(item.unit_price_cents) / 100.0
            quantity = float(item.quantity)
            
            lines.append({
                "Description": item.description,
                "Amount": amount_dollars,
                "DetailType": "SalesItemLineDetail",
                "SalesItemLineDetail": {
                    "ItemRef": {
                        "value": qbo_item_id
                    },
                    "Qty": quantity,
                    "UnitPrice": unit_price_dollars,
                    "TaxCodeRef": {
                        "value": "TAX" if item.is_taxable else "NON"
                    }
                }
            })
            
        invoice_payload = {
            "CustomerRef": {
                "value": qbo_customer_id
            },
            "DocNumber": invoice.invoice_number,
            "Line": lines,
            "PrivateNote": invoice.notes or ""
        }
        
        if invoice.tax_cents > 0:
            invoice_payload["TxnTaxDetail"] = {
                "TotalTax": float(invoice.tax_cents) / 100.0
            }
            
        create_res = self._api_request("POST", "invoice", json_data=invoice_payload)
        return create_res["Invoice"]["Id"]

    def create_payment(self, invoice: Invoice, qbo_invoice_id: str, qbo_customer_id: str) -> str:
        if self.is_mock:
            return f"mock_qbo_pmt_{invoice.id}"
            
        amount_dollars = float(invoice.amount_paid_cents) / 100.0
        payment_payload = {
            "CustomerRef": {
                "value": qbo_customer_id
            },
            "TotalAmt": amount_dollars,
            "Line": [
                {
                    "Amount": amount_dollars,
                    "LinkedTxn": [
                        {
                            "TxnId": qbo_invoice_id,
                            "TxnType": "Invoice"
                        }
                    ]
                }
            ]
        }
        
        create_res = self._api_request("POST", "payment", json_data=payment_payload)
        return create_res["Payment"]["Id"]

    def disconnect(self):
        if not self.is_mock and self.company.qbo_refresh_token:
            auth_str = f"{self.client_id}:{self.client_secret}"
            auth_b64 = base64.b64encode(auth_str.encode()).decode()
            
            headers = {
                "Authorization": f"Basic {auth_b64}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            data = {"token": self.company.qbo_refresh_token}
            try:
                httpx.post("https://developer.api.intuit.com/v2/oauth2/tokens/revoke", headers=headers, data=data)
            except Exception as e:
                logger.error(f"Error revoking QuickBooks token: {e}")
                
        self.company.qbo_realm_id = None
        self.company.qbo_access_token = None
        self.company.qbo_refresh_token = None
        self.company.qbo_token_expires_at = None
        
        self.db.add(self.company)
        self.db.flush()

    def _api_request(self, method: str, path: str, json_data: dict = None) -> dict:
        if not self.company.qbo_access_token:
            raise ValueError("Company is not connected to QuickBooks Online")
            
        stage = os.getenv("STAGE", "dev")
        use_sandbox = os.getenv("QBO_SANDBOX", "true").lower() == "true"
        
        if stage == "prod" and not use_sandbox:
            base_url = f"https://quickbooks.api.intuit.com/v3/company/{self.company.qbo_realm_id}"
        else:
            base_url = f"https://sandbox-quickbooks.api.intuit.com/v3/company/{self.company.qbo_realm_id}"
            
        url = f"{base_url}/{path}"
        headers = {
            "Authorization": f"Bearer {self.company.qbo_access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        params = {"minorversion": "65"}
        
        response = httpx.request(method, url, headers=headers, params=params, json=json_data, timeout=30.0)
        if response.status_code not in (200, 201):
            logger.error(f"QBO API Error ({response.status_code}) on {method} {path}: {response.text}")
            raise ValueError(f"QuickBooks API Error: {response.text}")
            
        return response.json()
