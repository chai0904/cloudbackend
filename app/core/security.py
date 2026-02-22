"""
Security module — Firebase JWT verification + Mock auth + Role guard + is_active enforcement.

Auth Flow:
1. User logs in via Firebase → gets JWT
2. Frontend sends JWT to FastAPI
3. FastAPI verifies JWT using Firebase Admin SDK
4. Backend fetches user profile from Supabase (by firebase_uid)
5. Backend checks: is user.is_active? is tenant.is_active?
6. Backend injects: user_id, role, tenant_id
7. Request proceeds with tenant isolation enforced

Only users registered by Institution Admin can log in.
Unknown Firebase UIDs are rejected.
"""

import os
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.core.config import settings
from app.core.database import get_supabase

security_scheme = HTTPBearer()

import bcrypt

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode('utf-8'), 
            hashed_password.encode('utf-8')
        )
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

# ---------------------------------------------------------------------------
# Firebase initialization (lazy)
# ---------------------------------------------------------------------------
_firebase_app = None


def _init_firebase():
    global _firebase_app
    if _firebase_app is not None:
        return
    import firebase_admin
    from firebase_admin import credentials as fb_credentials

    cred_path = settings.FIREBASE_CREDENTIALS_PATH
    if os.path.exists(cred_path):
        cred = fb_credentials.Certificate(cred_path)
        _firebase_app = firebase_admin.initialize_app(cred)
    else:
        # Try default credentials
        _firebase_app = firebase_admin.initialize_app()


# ---------------------------------------------------------------------------
# Mock users (for demo / hackathon fallback without Firebase)
# ---------------------------------------------------------------------------
MOCK_USERS = {
    "super-admin-token": {
        "uid": "sa-firebase-uid",
        "email": "superadmin@edunexis.in",
        "role": "super_admin",
        "tenant_id": None,
        "name": "Super Admin",
        "user_id": "a0000000-0000-0000-0000-000000000001",
    },
}


def _build_mock_users_from_db():
    """Load registered users from Supabase and create mock tokens for them."""
    try:
        db = get_supabase()
        result = db.table("users").select("*").eq("is_active", True).execute()
        if result.data:
            for user in result.data:
                token_key = f"mock-{user['email']}"
                MOCK_USERS[token_key] = {
                    "uid": user.get("firebase_uid", user["id"]),
                    "email": user["email"],
                    "role": user["role"],
                    "tenant_id": user.get("tenant_id"),
                    "name": user["name"],
                    "user_id": user["id"],
                    "department_id": user.get("department_id"),
                }
    except Exception:
        pass  # DB not yet connected — use hardcoded mock users


# ---------------------------------------------------------------------------
# Token verification — the core auth function
# ---------------------------------------------------------------------------
async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
) -> dict:
    """
    Validate the Bearer token and return user dict.
    Enforces: is_active user, is_active tenant.
    Only users already registered in Supabase can authenticate.
    """
    token = credentials.credentials

    if settings.AUTH_MODE == "mock":
        return await _mock_auth(token)

    return await _firebase_auth(token)


async def _mock_auth(token: str) -> dict:
    """Mock mode: look up token in MOCK_USERS dict or try DB lookup."""
    # Try direct token match
    user = MOCK_USERS.get(token)
    if user:
        return user

    # Try as email-based token: "mock-email@example.com"
    if token.startswith("mock-"):
        email = token[5:]
        try:
            db = get_supabase()
            result = (
                db.table("users")
                .select("*, tenants(is_active, subscription_plan)")
                .eq("email", email)
                .eq("is_active", True)
                .maybe_single()
                .execute()
            )
            if result.data:
                user_data = result.data
                tenant_info = user_data.get("tenants")

                # Check tenant is active (unless super_admin)
                if user_data["role"] != "super_admin" and tenant_info:
                    if not tenant_info.get("is_active", True):
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="Your institution's account has been deactivated",
                        )

                return {
                    "uid": user_data.get("firebase_uid", user_data["id"]),
                    "email": user_data["email"],
                    "role": user_data["role"],
                    "tenant_id": user_data.get("tenant_id"),
                    "name": user_data["name"],
                    "user_id": user_data["id"],
                    "department_id": user_data.get("department_id"),
                }
        except HTTPException:
            raise
        except Exception:
            pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid token. Only registered institutional users can login.",
    )


async def _firebase_auth(token: str) -> dict:
    """Firebase mode: verify JWT, fetch profile from Supabase, enforce is_active."""
    _init_firebase()
    from firebase_admin import auth as fb_auth

    try:
        decoded = fb_auth.verify_id_token(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Firebase token",
        )

    uid = decoded["uid"]

    # Fetch user profile from Supabase — MUST exist (admin-created users only)
    db = get_supabase()
    result = (
        db.table("users")
        .select("*, tenants(is_active, subscription_plan)")
        .eq("firebase_uid", uid)
        .maybe_single()
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not registered in any institution. Contact your institution admin.",
        )

    user_data = result.data

    # Check user is active
    if not user_data.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated. Contact your institution admin.",
        )

    # Check tenant is active (skip for super_admin)
    tenant_info = user_data.get("tenants")
    if user_data["role"] != "super_admin" and tenant_info:
        if not tenant_info.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your institution's account has been deactivated.",
            )

    return {
        "uid": uid,
        "email": user_data.get("email", decoded.get("email", "")),
        "role": user_data["role"],
        "tenant_id": user_data.get("tenant_id"),
        "name": user_data.get("name", ""),
        "user_id": user_data["id"],
        "department_id": user_data.get("department_id"),
    }


# ---------------------------------------------------------------------------
# Role guard dependency
# ---------------------------------------------------------------------------
def require_role(allowed_roles: list[str]):
    """
    Usage:
        @router.get("/admin-only")
        async def endpoint(user=Depends(require_role(["admin", "super_admin"]))):
    """

    async def role_checker(
        user: dict = Depends(get_current_user),
    ) -> dict:
        if user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user['role']}' not authorized. Required: {allowed_roles}",
            )
        return user

    return role_checker
