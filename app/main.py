"""
EduNexis — Multi-Tenant Academic ERP Backend
FastAPI entry point.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.middleware import TenantMiddleware
from app.routers import auth, admin, faculty, hod, student, compliance, institution, billing, assignments, assessments

app = FastAPI(
    title=settings.APP_NAME,
    description="Multi-Tenant Workflow & Compliance ERP for Indian Higher Education",
    version="1.0.0",
    debug=True,
)

# CORS
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tenant isolation middleware
app.add_middleware(TenantMiddleware)

# Include routers
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(faculty.router)
app.include_router(hod.router)
app.include_router(student.router)
app.include_router(compliance.router)
app.include_router(institution.router)
app.include_router(billing.router)
app.include_router(assignments.router)
app.include_router(assessments.router)


@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": "1.0.0",
        "status": "running",
        "auth_mode": settings.AUTH_MODE,
    }


@app.get("/api/health")
async def health():
    return {"status": "healthy", "auth_mode": settings.AUTH_MODE}
