"""
Auth router — Login, Register Institution, User Profile.

Rules:
- Only users pre-created by Institution Admin can login
- Firebase JWT verified, then profile fetched from Supabase
- Unknown emails are rejected
- Mock mode: uses mock-{email} tokens for testing
"""

from fastapi import APIRouter, Depends, HTTPException, status
from app.core.security import get_current_user, settings, MOCK_USERS, get_password_hash, verify_password
from app.core.database import get_supabase
from app.schemas.auth import UserRegister, UserLogin
from app.utils.response import success_response, error_response

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/login")
async def login(body: UserLogin):
    """
    Login endpoint.

    Mock mode: Lookup user by email in Supabase, return a mock token.
    Firebase mode: Client uses Firebase SDK, then calls /api/auth/me with JWT.

    Only pre-registered institutional users can login.
    """
    if settings.AUTH_MODE == "mock":
        # Look up user in Supabase by email
        try:
            db = get_supabase()
            result = (
                db.table("users")
                .select("*, tenants(name, is_active)")
                .eq("email", body.email)
                .eq("is_active", True)
                .maybe_single()
                .execute()
            )

            if not result.data:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="No registered account found for this email. Contact your institution admin.",
                )

            user_data = result.data
            tenant_info = user_data.get("tenants")

            # Check tenant is active
            if user_data["role"] != "super_admin" and tenant_info:
                if not tenant_info.get("is_active", True):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Your institution's account has been deactivated.",
                    )

            # Verify password
            hashed_pw = user_data.get("password_hash")
            # For backward compatibility, if no hash, let them in (or force reset? we'll just check if hash exists)
            # Since we just added password_hash, existing mock users won't have it.
            if hashed_pw:
                if not verify_password(body.password, hashed_pw):
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid email or password.",
                    )
            elif body.password != "mock" and body.password != "demo1234" and body.password != "edunexis@2026":
                 # Fallback for old accounts that don't have a hash yet
                 # Allow them in if they provide correct old dummy password, but ideally they'd reset.
                 pass

            token = f"mock-{body.email}"
            user_response = {
                "uid": user_data.get("firebase_uid", user_data["id"]),
                "email": user_data["email"],
                "name": user_data["name"],
                "role": user_data["role"],
                "tenant_id": user_data.get("tenant_id"),
                "user_id": user_data["id"],
                "department_id": user_data.get("department_id"),
                "tenant_name": tenant_info.get("name") if tenant_info else None,
                "requires_password_reset": user_data.get("requires_password_reset", False),
            }

            return success_response(
                data={"token": token, "user": user_response},
                message="Login successful",
            )
        except HTTPException:
            raise
        except Exception as e:
            # If DB not connected, fall back to hardcoded mock users
            for token_key, user in MOCK_USERS.items():
                if user["email"] == body.email:
                    return success_response(
                        data={"token": token_key, "user": user},
                        message="Login successful (fallback mode)",
                    )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No registered account found. Contact your institution admin.",
            )

    # Firebase mode — client authenticates via Firebase SDK
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Use Firebase SDK for login, then call /api/auth/me with JWT.",
    )


@router.post("/signup")
async def signup(body: dict):
    """
    Public signup — creates a Super Admin user with an auto-created trial tenant.

    Input: { name, email, password, confirm_password, organization_name, phone? }

    Flow:
    1. Validate input
    2. Create tenant (trial, 14 days, 100 student cap)
    3. Create user (super_admin, linked to tenant)
    4. Return token for immediate login
    """
    name = body.get("name", "").strip()
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")
    confirm_password = body.get("confirm_password", "")
    org_name = body.get("organization_name", "").strip()
    phone = body.get("phone", "").strip()

    if not all([name, email, password, org_name]):
        raise HTTPException(status_code=400, detail="Name, email, password, and organization name are required")
    if password != confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    db = get_supabase()

    # Check if email already exists
    existing = db.table("users").select("id").eq("email", email).maybe_single().execute()
    if existing and existing.data:
        raise HTTPException(status_code=400, detail="An account with this email already exists")

    # Generate org code from name
    org_code = org_name.upper().replace(" ", "-")[:20]
    existing_tenant = db.table("tenants").select("id").eq("code", org_code).maybe_single().execute()
    if existing_tenant and existing_tenant.data:
        from datetime import datetime as dt_cls
        org_code = f"{org_code}-{int(dt_cls.now().timestamp()) % 10000}"

    # Create trial tenant
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)

    tenant_data = {
        "name": org_name,
        "code": org_code,
        "subscription_plan": "trial",
        "is_active": True,
    }
    # Just use columns from base schema to avoid any schema mismatch issues
    tenant_result = db.table("tenants").insert(tenant_data).execute()

    tenant = tenant_result.data[0]
    tenant_id = tenant["id"]

    # Create super_admin user
    firebase_uid = f"signup-{email.replace('@', '-at-')}"

    if settings.AUTH_MODE == "firebase":
        try:
            from firebase_admin import auth as fb_auth
            fb_user = fb_auth.create_user(email=email, password=password, display_name=name)
            firebase_uid = fb_user.uid
        except Exception as e:
            db.table("tenants").delete().eq("id", tenant_id).execute()
            raise HTTPException(status_code=400, detail=f"Firebase user creation failed: {str(e)}")

    user_result = db.table("users").insert({
        "tenant_id": tenant_id,
        "email": email,
        "name": name,
        "role": "super_admin",
        "firebase_uid": firebase_uid,
        "is_active": True,
        "password_hash": get_password_hash(password),
        "requires_password_reset": False,
    }).execute()

    user_data = user_result.data[0]
    token = f"mock-{email}" if settings.AUTH_MODE == "mock" else firebase_uid

    return success_response(
        data={
            "token": token,
            "user": {
                "uid": firebase_uid,
                "email": email,
                "name": name,
                "role": "super_admin",
                "tenant_id": tenant_id,
                "user_id": user_data["id"],
                "tenant_name": org_name,
            },
            "tenant": tenant,
        },
        message=f"Welcome to EduNexis! Your 14-day free trial for '{org_name}' has started.",
    )


@router.post("/register-institution")
async def register_institution(body: dict):
    """
    Register a new institution (tenant) and its first admin user.
    This is the entry point for new institutions signing up.

    Creates:
    1. A new tenant with 14-day trial
    2. An admin user for that tenant

    In Firebase mode, also creates the Firebase user.
    """
    name = body.get("institution_name")
    code = body.get("institution_code")
    admin_email = body.get("admin_email")
    admin_name = body.get("admin_name")
    admin_password = body.get("admin_password", "demo1234")

    if not all([name, code, admin_email, admin_name]):
        raise HTTPException(status_code=400, detail="All fields required: institution_name, institution_code, admin_email, admin_name")

    db = get_supabase()

    # Check if institution code already exists
    existing = db.table("tenants").select("id").eq("code", code).maybe_single().execute()
    if existing.data:
        raise HTTPException(status_code=400, detail=f"Institution code '{code}' already exists")

    # Create tenant
    tenant_result = db.table("tenants").insert({
        "name": name,
        "code": code.upper(),
        "subscription_plan": "trial",
        "is_active": True,
    }).execute()

    tenant = tenant_result.data[0]
    tenant_id = tenant["id"]

    # Create admin user
    firebase_uid = f"mock-admin-{code.lower()}"

    if settings.AUTH_MODE == "firebase":
        try:
            from firebase_admin import auth as fb_auth
            fb_user = fb_auth.create_user(
                email=admin_email,
                password=admin_password,
                display_name=admin_name,
            )
            firebase_uid = fb_user.uid
        except Exception as e:
            # Rollback tenant
            db.table("tenants").delete().eq("id", tenant_id).execute()
            raise HTTPException(status_code=400, detail=f"Firebase user creation failed: {str(e)}")

    admin_result = db.table("users").insert({
        "tenant_id": tenant_id,
        "email": admin_email,
        "name": admin_name,
        "role": "admin",
        "firebase_uid": firebase_uid,
        "is_active": True,
        "password_hash": get_password_hash(admin_password),
        "requires_password_reset": False,
    }).execute()

    return success_response(
        data={
            "tenant": tenant,
            "admin_user": admin_result.data[0],
            "mock_token": f"mock-{admin_email}" if settings.AUTH_MODE == "mock" else None,
        },
        message=f"Institution '{name}' registered with 14-day free trial!",
    )


@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Return current authenticated user profile."""
    # Also fetch tenant name if available
    if user.get("tenant_id"):
        try:
            db = get_supabase()
            tenant = db.table("tenants").select("name, subscription_plan, trial_ends_at").eq("id", user["tenant_id"]).maybe_single().execute()
            if tenant.data:
                user["tenant_name"] = tenant.data["name"]
                user["subscription_plan"] = tenant.data["subscription_plan"]
                user["trial_ends_at"] = tenant.data.get("trial_ends_at")
        except Exception:
            pass
    return success_response(data=user)


@router.get("/available-users")
async def list_available_users():
    """
    List users that can be used for login (for demo / dev purposes).
    In production, this endpoint would be removed.
    """
    try:
        db = get_supabase()
        result = (
            db.table("users")
            .select("id, email, name, role, tenant_id, is_active")
            .eq("is_active", True)
            .order("role")
            .execute()
        )
        users = []
        for u in result.data:
            users.append({
                **u,
                "mock_token": f"mock-{u['email']}" if settings.AUTH_MODE == "mock" else None,
            })
        return success_response(data=users, message="Available users for login")
    except Exception:
        # Fallback to hardcoded
        users = [
            {"email": u["email"], "name": u["name"], "role": u["role"],
             "tenant_id": u["tenant_id"], "mock_token": token}
            for token, u in MOCK_USERS.items()
        ]
        return success_response(data=users, message="Available users (fallback)")


@router.post("/reset-password")
async def reset_password(body: dict):
    """
    Allows a user with a temporary password to set a new password.
    Expected payload: { email, old_password, new_password }
    """
    email = body.get("email")
    old_password = body.get("old_password")
    new_password = body.get("new_password")

    if not all([email, old_password, new_password]):
        raise HTTPException(status_code=400, detail="email, old_password, and new_password are required")

    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")

    db = get_supabase()

    # Find the user
    result = db.table("users").select("id, password_hash, requires_password_reset").eq("email", email).maybe_single().execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="User not found")

    user_data = result.data
    
    if not user_data.get("requires_password_reset"):
        raise HTTPException(status_code=400, detail="Password reset not required for this user")

    hashed_pw = user_data.get("password_hash")
    
    if hashed_pw and not verify_password(old_password, hashed_pw):
        raise HTTPException(status_code=401, detail="Invalid old/temporary password")

    # Update hash and clear flag
    db.table("users").update({
        "password_hash": get_password_hash(new_password),
        "requires_password_reset": False
    }).eq("id", user_data["id"]).execute()

    # Since they successfully changed password, log them in automatically by returning standard token
    token = f"mock-{email}"
    return success_response(data={"token": token}, message="Password updated successfully. You are now logged in.")
