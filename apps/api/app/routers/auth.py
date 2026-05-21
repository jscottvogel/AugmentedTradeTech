import os
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
import pyotp
import boto3
import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Response, Request, Cookie
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import select, text

from apps.api.app.core.database import get_db
from apps.api.app.models.user import User
from apps.api.app.models.auth import MagicLinkToken, RefreshToken

router = APIRouter(prefix="/auth", tags=["auth"])

# Cryptography and Token configuration
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-key-for-local-dev-only-change-in-prod")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 30

# Pydantic Schemas for Requests/Responses
class LookupRequest(BaseModel):
    email: EmailStr

class MagicLinkRequest(BaseModel):
    email: EmailStr

class MagicLinkVerifyRequest(BaseModel):
    token: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    mfa_token: Optional[str] = None

class RefreshRequest(BaseModel):
    pass

class MfaEnableRequest(BaseModel):
    token: str

# Helper Functions
def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def create_access_token(user_id: str, company_id: Optional[str], role: str, email: str, is_active: bool) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "sub": user_id,
        "user_id": user_id,
        "company_id": company_id,
        "role": role,
        "email": email,
        "is_active": is_active,
        "exp": expire
    }
    return jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)

def send_ses_email(email: str, token: str) -> bool:
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    verify_url = f"{frontend_url}/auth/verify?token={token}"
    
    subject = "Augmented Trade Tech - Your Magic Login Link"
    body_text = f"Hello,\n\nClick the link below to log in to Augmented Trade Tech:\n\n{verify_url}\n\nThis link is valid for 15 minutes and can only be used once."
    body_html = f"""<html>
    <body>
      <h3>Augmented Trade Tech</h3>
      <p>Click the link below to log in to your account:</p>
      <p><a href="{verify_url}"><strong>Log In to App</strong></a></p>
      <p>Or copy and paste this URL into your browser:</p>
      <p>{verify_url}</p>
      <br/>
      <p>This link is valid for 15 minutes and can only be used once.</p>
    </body>
    </html>"""
    
    # If in local dev or AWS credentials not present, print link to console
    if os.getenv("STAGE", "dev") == "dev" and not os.getenv("AWS_ACCESS_KEY_ID"):
        print(f"\n[LOCAL DEV] Sending Magic Link to {email}:\n{verify_url}\n")
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
        print(f"Error sending email via SES: {e}")
        # Fallback to printing in dev
        if os.getenv("STAGE", "dev") == "dev":
            print(f"\n[FALLBACK] Magic Link for {email}: {verify_url}\n")
        return False

# Auth Endpoints

@router.post("/lookup")
def lookup_user(req: LookupRequest, db: Session = Depends(get_db)):
    """Check if the user exists and determine their auth path based on role"""
    db.execute(text("SELECT set_config('app.current_role', 'platform_admin', true)"))
    user = db.scalar(select(User).where(User.email == req.email.lower(), User.is_active == True))
    if not user:
        return {"exists": False}
    
    auth_method = "magic_link" if user.role == "tech" else "password"
    return {
        "exists": True,
        "role": user.role,
        "auth_method": auth_method,
        "mfa_enabled": user.mfa_enabled
    }

@router.post("/magic-link")
def send_magic_link(req: MagicLinkRequest, db: Session = Depends(get_db)):
    """Generate and email a magic link to a technician"""
    db.execute(text("SELECT set_config('app.current_role', 'platform_admin', true)"))
    user = db.scalar(
        select(User).where(
            User.email == req.email.lower(),
            (User.is_active == True) | (User.last_login_at.is_(None))
        )
    )
    if not user:
        # Prevent email enumeration by returning success anyway
        return {"message": "If the email is registered, a magic link has been sent."}
    
    if user.role != "tech":
        raise HTTPException(status_code=400, detail="Only technicians can log in via magic links")

    raw_token = secrets.token_hex(32)
    token_hashed = hash_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

    magic_token = MagicLinkToken(
        user_id=user.id,
        token_hash=token_hashed,
        expires_at=expires_at,
        created_by=user.id,
        updated_by=user.id
    )
    db.add(magic_token)
    db.commit()

    send_ses_email(user.email, raw_token)

    return {"message": "If the email is registered, a magic link has been sent."}

@router.post("/magic-link/verify")
def verify_magic_link(req: MagicLinkVerifyRequest, response: Response, db: Session = Depends(get_db)):
    """Verify magic link token and set refresh token cookie + return access token"""
    db.execute(text("SELECT set_config('app.current_role', 'platform_admin', true)"))
    token_hashed = hash_token(req.token)
    magic_token = db.scalar(
        select(MagicLinkToken).where(
            MagicLinkToken.token_hash == token_hashed,
            MagicLinkToken.used_at.is_(None)
        )
    )

    if not magic_token:
        raise HTTPException(status_code=400, detail="Invalid or already used magic link")

    if magic_token.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Expired magic link")

    # Mark as used
    magic_token.used_at = datetime.now(timezone.utc)
    user = magic_token.user

    # Check for deactivation
    if not user.is_active and (user.last_login_at is not None or user.full_name != ""):
        raise HTTPException(status_code=403, detail="Deactivated user account")

    # Update last login
    user.last_login_at = datetime.now(timezone.utc)
    
    # Generate tokens
    access_token = create_access_token(user.id, user.company_id, user.role, user.email, user.is_active)
    
    raw_refresh = secrets.token_hex(32)
    refresh_hashed = hash_token(raw_refresh)
    refresh_expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    refresh_token_record = RefreshToken(
        user_id=user.id,
        token_hash=refresh_hashed,
        expires_at=refresh_expire,
        created_by=user.id,
        updated_by=user.id
    )
    db.add(refresh_token_record)
    db.commit()

    # Set httpOnly cookie for refresh token
    response.set_cookie(
        key="refresh_token",
        value=raw_refresh,
        httponly=True,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        expires=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        secure=True,
        samesite="lax",
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "full_name": user.full_name,
            "company_id": user.company_id,
            "is_active": user.is_active,
        }
    }

@router.post("/login")
def login_password(req: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """Authenticate admin or dispatcher using email/password + optional MFA"""
    db.execute(text("SELECT set_config('app.current_role', 'platform_admin', true)"))
    user = db.scalar(select(User).where(User.email == req.email.lower(), User.is_active == True))
    
    if not user or user.role == "tech":
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.password_hash or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # If MFA is enabled, verify the TOTP token
    if user.mfa_enabled:
        if not req.mfa_token:
            raise HTTPException(status_code=400, detail="MFA token is required")
        totp = pyotp.TOTP(user.mfa_secret)
        if not totp.verify(req.mfa_token):
            raise HTTPException(status_code=401, detail="Invalid MFA token")

    # Update last login
    user.last_login_at = datetime.now(timezone.utc)
    
    # Generate tokens
    access_token = create_access_token(user.id, user.company_id, user.role, user.email, user.is_active)
    
    raw_refresh = secrets.token_hex(32)
    refresh_hashed = hash_token(raw_refresh)
    refresh_expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    refresh_token_record = RefreshToken(
        user_id=user.id,
        token_hash=refresh_hashed,
        expires_at=refresh_expire,
        created_by=user.id,
        updated_by=user.id
    )
    db.add(refresh_token_record)
    db.commit()

    response.set_cookie(
        key="refresh_token",
        value=raw_refresh,
        httponly=True,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        expires=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        secure=True,
        samesite="lax",
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "full_name": user.full_name,
            "company_id": user.company_id,
            "is_active": user.is_active,
        }
    }

@router.post("/refresh")
def refresh_token(response: Response, refresh_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    """Refresh the access token using the httpOnly refresh token cookie"""
    db.execute(text("SELECT set_config('app.current_role', 'platform_admin', true)"))
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token missing")

    token_hashed = hash_token(refresh_token)
    db_token = db.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hashed
        )
    )

    if not db_token:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if db_token.expires_at < datetime.now(timezone.utc):
        db.delete(db_token)
        db.commit()
        raise HTTPException(status_code=401, detail="Expired refresh token")

    # Refresh token is valid: rotate it (delete old, generate new)
    user = db_token.user
    db.delete(db_token)

    access_token = create_access_token(user.id, user.company_id, user.role, user.email, user.is_active)
    
    raw_refresh = secrets.token_hex(32)
    refresh_hashed = hash_token(raw_refresh)
    refresh_expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    new_refresh_record = RefreshToken(
        user_id=user.id,
        token_hash=refresh_hashed,
        expires_at=refresh_expire,
        created_by=user.id,
        updated_by=user.id
    )
    db.add(new_refresh_record)
    db.commit()

    response.set_cookie(
        key="refresh_token",
        value=raw_refresh,
        httponly=True,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        expires=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        secure=True,
        samesite="lax",
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "full_name": user.full_name,
            "company_id": user.company_id,
            "is_active": user.is_active,
        }
    }

@router.post("/logout")
def logout_user(response: Response, refresh_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    """Log the user out by deleting their refresh token from DB and clearing the cookie"""
    if refresh_token:
        token_hashed = hash_token(refresh_token)
        db_token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hashed))
        if db_token:
            db.delete(db_token)
            db.commit()

    response.delete_cookie(key="refresh_token")
    return {"message": "Logged out successfully"}

# MFA Setup Endpoints (Protected routes requiring request.state.user context)

@router.post("/mfa/setup")
def mfa_setup(request: Request, db: Session = Depends(get_db)):
    """Generate a TOTP secret and return the setup configuration URI"""
    user_state = getattr(request.state, "user", None)
    if not user_state:
        raise HTTPException(status_code=401, detail="Unauthorized")

    user = db.scalar(select(User).where(User.id == user_state["user_id"]))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Generate a new secret if the user doesn't already have one
    if not user.mfa_secret:
        user.mfa_secret = pyotp.random_base32()
        db.commit()

    totp = pyotp.TOTP(user.mfa_secret)
    # Generate provisioning URI for QR codes
    provisioning_uri = totp.provisioning_uri(name=user.email, issuer_name="AugmentedTradeTech")

    return {
        "secret": user.mfa_secret,
        "provisioning_uri": provisioning_uri
    }

@router.post("/mfa/enable")
def mfa_enable(req: MfaEnableRequest, request: Request, db: Session = Depends(get_db)):
    """Verify TOTP token and enable MFA on the user account"""
    user_state = getattr(request.state, "user", None)
    if not user_state:
        raise HTTPException(status_code=401, detail="Unauthorized")

    user = db.scalar(select(User).where(User.id == user_state["user_id"]))
    if not user or not user.mfa_secret:
        raise HTTPException(status_code=400, detail="MFA setup was not initiated")

    totp = pyotp.TOTP(user.mfa_secret)
    if not totp.verify(req.token):
        raise HTTPException(status_code=400, detail="Invalid MFA token")

    user.mfa_enabled = True
    db.commit()

    return {"message": "MFA has been successfully enabled"}
