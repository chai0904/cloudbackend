"""
Subscription enforcement guards.

Usage:
    from app.core.subscription import check_subscription, check_student_limit

    @router.post("/students")
    async def create_student(...):
        check_subscription(tenant_id)
        check_student_limit(tenant_id)
        ...
"""

from datetime import datetime, timezone
from fastapi import HTTPException, status
from app.core.database import get_supabase


def check_subscription(tenant_id: str):
    """
    Verify tenant has an active subscription or is within trial period.
    Raises 403 if trial expired and no paid plan.
    """
    if not tenant_id:
        return  # super_admin without tenant

    db = get_supabase()
    tenant = (
        db.table("tenants")
        .select("subscription_plan, trial_ends_at, is_active")
        .eq("id", tenant_id)
        .execute()
    )

    if not tenant.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    t = tenant.data[0]
    if not t.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your institution account has been deactivated.",
        )

    plan = t.get("subscription_plan", "trial")

    if plan == "trial":
        trial_ends = t.get("trial_ends_at")
        if trial_ends:
            # Parse ISO timestamp
            if isinstance(trial_ends, str):
                trial_ends = datetime.fromisoformat(trial_ends.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > trial_ends:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Your 14-day free trial has expired. Please upgrade your plan to continue.",
                )


def check_student_limit(tenant_id: str):
    """
    Check if tenant has reached their student enrollment limit.
    Raises 403 if limit exceeded.
    """
    if not tenant_id:
        return

    db = get_supabase()

    # Get tenant limit
    tenant = (
        db.table("tenants")
        .select("max_students, student_limit, subscription_plan")
        .eq("id", tenant_id)
        .execute()
    )

    if not tenant.data:
        return

    t_data = tenant.data[0]
    limit = t_data.get("student_limit") or t_data.get("max_students") or 100

    # Count active students
    count_result = (
        db.table("users")
        .select("id")
        .eq("tenant_id", tenant_id)
        .eq("role", "student")
        .eq("is_active", True)
        .execute()
    )

    current_count = len(count_result.data) if count_result and count_result.data else 0

    if current_count >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Student limit reached ({current_count}/{limit}). Upgrade your plan to add more students.",
        )
