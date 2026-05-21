import sys
import os
import boto3
import logging
from datetime import datetime, timezone, timedelta, time
from sqlalchemy import select

# Add parent directory to sys.path to allow absolute imports in Lambda if needed
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")))

from apps.api.app.core.database import SessionLocal
from apps.api.app.models.membership import Membership, MembershipPlan
from apps.api.app.models.customer import Customer
from apps.api.app.models.company import Company

logger = logging.getLogger(__name__)

def publish_sns_notification(customer_phone: str | None, message: str):
    if not customer_phone:
        logger.warning("No customer phone number available for SNS notification")
        return
    try:
        sns = boto3.client("sns", region_name=os.getenv("AWS_REGION", "us-east-1"))
        sns.publish(
            PhoneNumber=customer_phone,
            Message=message
        )
        logger.info(f"Published SNS message to {customer_phone}: '{message}'")
    except Exception as e:
        logger.warning(f"Skipped SNS notification: {e} (AWS credentials likely not set up locally)")

def send_reminder_email(email: str, subject: str, body_text: str, body_html: str) -> bool:
    if os.getenv("STAGE", "dev") == "dev" and not os.getenv("AWS_ACCESS_KEY_ID"):
        print(f"\n[LOCAL DEV] Sending Email to {email}:\nSubject: {subject}\n{body_text}\n")
        return True
        
    try:
        ses = boto3.client("ses", region_name=os.getenv("AWS_REGION", "us-east-1"))
        sender = os.getenv("SES_SENDER_EMAIL", "noreply@augmentedtradetech.com")
        ses.send_email(
            Source=sender,
            Destination={"ToAddresses": [email]},
            Message={
                "Subject": {"Data": subject},
                "Body": {
                    "Text": {"Data": body_text},
                    "Html": {"Data": body_html}
                }
            }
        )
        return True
    except Exception as e:
        logger.error(f"Error sending email via SES: {e}")
        return False

def handler(event, context):
    """
    Daily cron job triggered by EventBridge.
    Sends 30-day and 7-day membership renewal reminders,
    and daily grace period notifications.
    """
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        today = now.date()

        # Define 30-day range (start of day to end of day)
        start_30 = datetime.combine(today + timedelta(days=30), time.min, tzinfo=timezone.utc)
        end_30 = datetime.combine(today + timedelta(days=30), time.max, tzinfo=timezone.utc)

        # Define 7-day range
        start_7 = datetime.combine(today + timedelta(days=7), time.min, tzinfo=timezone.utc)
        end_7 = datetime.combine(today + timedelta(days=7), time.max, tzinfo=timezone.utc)

        notifications_sent = 0

        # 1. Query for 30-day reminders
        mems_30 = db.scalars(
            select(Membership)
            .where(Membership.status == "active")
            .where(Membership.next_renewal_at >= start_30)
            .where(Membership.next_renewal_at <= end_30)
        ).all()

        for mem in mems_30:
            plan = db.scalar(select(MembershipPlan).where(MembershipPlan.id == mem.plan_id))
            customer = db.scalar(select(Customer).where(Customer.id == mem.customer_id))
            company = db.scalar(select(Company).where(Company.id == mem.company_id))
            
            if not customer or not company or not plan:
                continue

            customer_name = f"{customer.first_name} {customer.last_name}"
            renewal_date_str = mem.next_renewal_at.strftime("%Y-%m-%d")
            
            # Send 30-day reminder (white-labeled)
            subject = f"Your {plan.name} Membership Renewal - {company.name}"
            body_text = f"Hello {customer_name},\n\nThis is a friendly reminder that your membership '{plan.name}' with {company.name} will renew on {renewal_date_str}.\n\nThank you for your business!"
            body_html = f"""<html>
            <body>
              <h3>{company.name}</h3>
              <p>Hello <strong>{customer_name}</strong>,</p>
              <p>This is a friendly reminder that your membership <strong>{plan.name}</strong> with <strong>{company.name}</strong> will renew on <strong>{renewal_date_str}</strong>.</p>
              <br/>
              <p>Thank you for your business!</p>
            </body>
            </html>"""
            
            if customer.email:
                send_reminder_email(customer.email, subject, body_text, body_html)
                
            sms_message = f"{company.name}: Your membership {plan.name} will renew on {renewal_date_str}."
            publish_sns_notification(customer.phone, sms_message)
            notifications_sent += 1

        # 2. Query for 7-day reminders
        mems_7 = db.scalars(
            select(Membership)
            .where(Membership.status == "active")
            .where(Membership.next_renewal_at >= start_7)
            .where(Membership.next_renewal_at <= end_7)
        ).all()

        for mem in mems_7:
            plan = db.scalar(select(MembershipPlan).where(MembershipPlan.id == mem.plan_id))
            customer = db.scalar(select(Customer).where(Customer.id == mem.customer_id))
            company = db.scalar(select(Company).where(Company.id == mem.company_id))
            
            if not customer or not company or not plan:
                continue

            customer_name = f"{customer.first_name} {customer.last_name}"
            renewal_date_str = mem.next_renewal_at.strftime("%Y-%m-%d")
            
            # Send 7-day reminder (white-labeled)
            subject = f"Your {plan.name} Membership Renewal in 7 Days - {company.name}"
            body_text = f"Hello {customer_name},\n\nThis is a friendly reminder that your membership '{plan.name}' with {company.name} will renew in 7 days on {renewal_date_str}.\n\nThank you for your business!"
            body_html = f"""<html>
            <body>
              <h3>{company.name}</h3>
              <p>Hello <strong>{customer_name}</strong>,</p>
              <p>This is a friendly reminder that your membership <strong>{plan.name}</strong> with <strong>{company.name}</strong> will renew in 7 days on <strong>{renewal_date_str}</strong>.</p>
              <br/>
              <p>Thank you for your business!</p>
            </body>
            </html>"""
            
            if customer.email:
                send_reminder_email(customer.email, subject, body_text, body_html)
                
            sms_message = f"{company.name}: Your membership {plan.name} will renew in 7 days on {renewal_date_str}."
            publish_sns_notification(customer.phone, sms_message)
            notifications_sent += 1

        # 3. Query for grace period warning notifications
        mems_grace = db.scalars(
            select(Membership)
            .where(Membership.grace_period_ends_at > now)
        ).all()

        for mem in mems_grace:
            plan = db.scalar(select(MembershipPlan).where(MembershipPlan.id == mem.plan_id))
            customer = db.scalar(select(Customer).where(Customer.id == mem.customer_id))
            company = db.scalar(select(Company).where(Company.id == mem.company_id))
            
            if not customer or not company or not plan:
                continue

            customer_name = f"{customer.first_name} {customer.last_name}"
            grace_ends_str = mem.grace_period_ends_at.strftime("%Y-%m-%d")
            
            # Send grace period warning (white-labeled)
            subject = f"Action Required: Membership Payment Failed - {company.name}"
            body_text = f"Hello {customer_name},\n\nWe were unable to process your payment for your membership '{plan.name}'. Please update your payment information by {grace_ends_str} to prevent your membership from being suspended.\n\nThank you,\n{company.name}"
            body_html = f"""<html>
            <body>
              <h3>{company.name}</h3>
              <p>Hello <strong>{customer_name}</strong>,</p>
              <p>We were unable to process your payment for your membership <strong>{plan.name}</strong>.</p>
              <p>Please update your payment information by <strong>{grace_ends_str}</strong> to prevent your membership from being suspended.</p>
              <br/>
              <p>Thank you,</p>
              <p><strong>{company.name}</strong></p>
            </body>
            </html>"""
            
            if customer.email:
                send_reminder_email(customer.email, subject, body_text, body_html)
                
            sms_message = f"{company.name}: Action Required - Payment failed for membership {plan.name}. Please update your payment method by {grace_ends_str} to prevent suspension."
            publish_sns_notification(customer.phone, sms_message)
            notifications_sent += 1

        print(f"Cron membership reminder worker completed. Sent {notifications_sent} notification(s).")
        return {
            "status": "success",
            "notifications_sent": notifications_sent
        }

    except Exception as e:
        logger.error(f"Error in membership reminder cron handler: {e}")
        raise e
    finally:
        db.close()
