import jwt
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from mangum import Mangum

from fastapi.middleware.cors import CORSMiddleware

from apps.api.app.routers.auth import router as auth_router, JWT_SECRET, ALGORITHM
from apps.api.app.routers.onboarding import router as onboarding_router
from apps.api.app.routers.users import router as users_router
from apps.api.app.routers.me import router as me_router
from apps.api.app.routers.techs import router as techs_router
from apps.api.app.routers.jobs import router as jobs_router
from apps.api.app.routers.dispatch import router as dispatch_router
from apps.api.app.routers.customers import router as customers_router
from apps.api.app.routers.ai import router as ai_router, equipment_router
from apps.api.app.routers.invoices import router as invoices_router, webhook_router
from apps.api.app.routers.qbo import router as qbo_router
from apps.api.app.routers.portal import router as portal_router
from apps.api.app.routers.membership_plans import router as membership_plans_router
from apps.api.app.routers.memberships import router as memberships_router
from apps.api.app.routers.loyalty import router as loyalty_router

app = FastAPI(
    title="Augmented Trade Tech API",
    description="Wisdom in every work order - AI-powered field service platform backend",
    version="1.0.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(onboarding_router)
app.include_router(users_router)
app.include_router(me_router)
app.include_router(techs_router)
app.include_router(jobs_router)
app.include_router(dispatch_router)
app.include_router(customers_router)
app.include_router(ai_router)
app.include_router(equipment_router)
app.include_router(invoices_router)
app.include_router(webhook_router)
app.include_router(qbo_router)
app.include_router(portal_router)
app.include_router(membership_plans_router)
app.include_router(memberships_router)
app.include_router(loyalty_router)

PUBLIC_PREFIXES = ("/docs", "/redoc", "/openapi.json", "/mock-s3-upload")
PUBLIC_PATHS = {
    "/health",
    "/auth/lookup",
    "/auth/magic-link",
    "/auth/magic-link/verify",
    "/auth/login",
    "/auth/refresh",
    "/auth/logout",
    "/onboarding/company",
    "/webhooks/stripe",
    "/integrations/qbo/callback",
    "/portal/auth/magic-link",
    "/portal/auth/verify",
    "/portal/company-config"
}


@app.middleware("http")
async def add_rls_context_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path
    if path != "/" and path.endswith("/"):
        path = path[:-1]

    is_public = (
        path in PUBLIC_PATHS or 
        path.startswith(PUBLIC_PREFIXES) or 
        (path.startswith("/onboarding/") and path.endswith("/stripe/callback"))
    )
    auth_header = request.headers.get("Authorization")

    if not is_public:
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid authorization credentials"}
            )
        token = auth_header.split(" ")[1]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
            request.state.user_id = payload.get("user_id")
            request.state.customer_id = payload.get("customer_id")
            request.state.company_id = payload.get("company_id")
            request.state.role = payload.get("role")
            request.state.email = payload.get("email")
            request.state.user = payload
        except jwt.ExpiredSignatureError:
            return JSONResponse(status_code=401, content={"detail": "Token signature has expired"})
        except jwt.InvalidTokenError:
            return JSONResponse(status_code=401, content={"detail": "Invalid token"})
    else:
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            try:
                payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
                request.state.user_id = payload.get("user_id")
                request.state.customer_id = payload.get("customer_id")
                request.state.company_id = payload.get("company_id")
                request.state.role = payload.get("role")
                request.state.email = payload.get("email")
                request.state.user = payload
            except Exception:
                pass

    response = await call_next(request)
    return response

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "augmented-trade-tech-backend"
    }

@app.put("/mock-s3-upload/{path:path}")
async def mock_s3_upload(path: str, request: Request):
    """Mock receiver endpoint representing direct S3 PUT uploads during local development"""
    body = await request.body()
    return {"status": "success", "s3_key": path, "size_bytes": len(body)}

# Wrap with Mangum for AWS Lambda integration in production
handler = Mangum(app)
