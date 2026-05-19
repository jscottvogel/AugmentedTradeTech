from fastapi import FastAPI, Request
from mangum import Mangum

app = FastAPI(
    title="Augmented Trade Tech API",
    description="Wisdom in every work order - AI-powered field service platform backend",
    version="1.0.0",
)

@app.middleware("http")
async def add_rls_context_middleware(request: Request, call_next):
    request.state.company_id = request.headers.get("X-Company-ID")
    request.state.user_id = request.headers.get("X-User-ID")
    request.state.role = request.headers.get("X-Role")
    response = await call_next(request)
    return response

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "augmented-trade-tech-backend"
    }

# Wrap with Mangum for AWS Lambda integration in production
handler = Mangum(app)
