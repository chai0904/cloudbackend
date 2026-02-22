"""
Billing router — Usage tracking, price calculation, plan activation, billing history.

Pricing:
    Starter  — ₹4,999/mo  (up to 500 students)
    Pro      — ₹12,999/mo  (up to 3000 students)
    Enterprise — Custom

Overage: ₹5 per additional student/month beyond plan limit.
"""

from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from app.core.security import require_role
from app.core.database import get_supabase
from app.utils.response import success_response

router = APIRouter(prefix="/api/billing", tags=["Billing"])

PLANS = {
    "trial":      {"label": "Free Trial",  "price": 0,     "student_limit": 100,  "duration_days": 14},
    "starter":    {"label": "Starter",     "price": 4999,  "student_limit": 500,  "duration_days": 30},
    "pro":        {"label": "Pro",         "price": 12999, "student_limit": 3000, "duration_days": 30},
    "enterprise": {"label": "Enterprise",  "price": 49999, "student_limit": 99999, "duration_days": 30},
}

OVERAGE_RATE = 5  # ₹5 per extra student/month


@router.get("/plans")
async def list_plans(user: dict = Depends(require_role(["admin", "super_admin"]))):
    """Return available plans with pricing."""
    return success_response(data=PLANS)


@router.get("/usage")
async def get_usage(user: dict = Depends(require_role(["admin", "super_admin"]))):
    """Get current student usage, plan status, and trial info for the tenant."""
    tenant_id = user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant associated")

    db = get_supabase()

    # Tenant info
    tenant = (
        db.table("tenants")
        .select("name, subscription_plan, max_students, student_limit, trial_started_at, trial_ends_at, is_active")
        .eq("id", tenant_id)
        .maybe_single()
        .execute()
    )
    if not tenant.data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    t = tenant.data
    plan = t.get("subscription_plan", "trial")
    limit = t.get("student_limit") or t.get("max_students") or 100

    # Count active students
    count_result = (
        db.table("users")
        .select("id", count="exact")
        .eq("tenant_id", tenant_id)
        .eq("role", "student")
        .eq("is_active", True)
        .execute()
    )
    active_students = count_result.count if count_result.count is not None else 0

    # Trial days remaining
    trial_days_remaining = None
    trial_expired = False
    if plan == "trial":
        trial_ends = t.get("trial_ends_at")
        if trial_ends:
            if isinstance(trial_ends, str):
                trial_ends_dt = datetime.fromisoformat(trial_ends.replace("Z", "+00:00"))
            else:
                trial_ends_dt = trial_ends
            remaining = (trial_ends_dt - datetime.now(timezone.utc)).days
            trial_days_remaining = max(remaining, 0)
            trial_expired = remaining < 0

    return success_response(data={
        "tenant_name": t.get("name"),
        "plan": plan,
        "plan_label": PLANS.get(plan, {}).get("label", plan),
        "student_limit": limit,
        "active_students": active_students,
        "usage_percentage": round((active_students / limit) * 100, 1) if limit > 0 else 0,
        "trial_days_remaining": trial_days_remaining,
        "trial_expired": trial_expired,
        "trial_ends_at": t.get("trial_ends_at"),
        "is_active": t.get("is_active"),
    })


@router.post("/calculate")
async def calculate_billing(
    body: dict,
    user: dict = Depends(require_role(["admin", "super_admin"])),
):
    """
    Calculate billing for a selected plan.
    Input: { selected_plan, promo_code? }
    """
    tenant_id = user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant associated")

    selected_plan = body.get("selected_plan", "starter")
    promo_code = body.get("promo_code", "").strip().upper()

    if selected_plan not in PLANS:
        raise HTTPException(status_code=400, detail=f"Invalid plan: {selected_plan}")

    plan_info = PLANS[selected_plan]
    base_price = plan_info["price"]
    new_limit = plan_info["student_limit"]

    db = get_supabase()

    # Count active students
    count_result = (
        db.table("users")
        .select("id", count="exact")
        .eq("tenant_id", tenant_id)
        .eq("role", "student")
        .eq("is_active", True)
        .execute()
    )
    active_students = count_result.count if count_result.count is not None else 0

    # Overage calculation
    overage_charge = 0
    overage_students = 0
    if active_students > new_limit:
        overage_students = active_students - new_limit
        overage_charge = overage_students * OVERAGE_RATE

    # Promo code
    discount = 0
    promo_message = None
    if promo_code:
        promo = (
            db.table("promo_codes")
            .select("*")
            .eq("code", promo_code)
            .eq("is_active", True)
            .maybe_single()
            .execute()
        )
        if promo.data:
            p = promo.data
            # Check expiry
            if p.get("expires_at"):
                exp = datetime.fromisoformat(p["expires_at"].replace("Z", "+00:00"))
                if datetime.now(timezone.utc) > exp:
                    promo_message = "Promo code has expired"
                    promo_code = ""
            if promo_code:
                if p["discount_type"] == "percentage":
                    discount = (base_price + overage_charge) * (p["discount_value"] / 100)
                    promo_message = f"{p['code']} Applied – {int(p['discount_value'])}% Discount"
                else:
                    discount = min(p["discount_value"], base_price + overage_charge)
                    promo_message = f"{p['code']} Applied – ₹{int(p['discount_value'])} Off"
        else:
            promo_message = "Invalid promo code"
            promo_code = ""

    final_amount = max(0, base_price + overage_charge - discount)

    return success_response(data={
        "selected_plan": selected_plan,
        "plan_label": plan_info["label"],
        "base_price": base_price,
        "active_students": active_students,
        "new_student_limit": new_limit,
        "overage_students": overage_students,
        "overage_charge": overage_charge,
        "discount": round(discount, 2),
        "promo_code": promo_code if promo_code else None,
        "promo_message": promo_message,
        "final_amount": round(final_amount, 2),
        "no_payment_required": final_amount == 0,
    })


@router.post("/subscribe")
async def subscribe(
    body: dict,
    user: dict = Depends(require_role(["admin", "super_admin"])),
):
    """
    Activate a subscription plan (dummy payment).
    Input: { selected_plan, promo_code? }
    """
    tenant_id = user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant associated")

    selected_plan = body.get("selected_plan", "starter")
    promo_code = body.get("promo_code", "").strip().upper()

    if selected_plan not in PLANS or selected_plan == "trial":
        raise HTTPException(status_code=400, detail="Invalid plan for subscription")

    plan_info = PLANS[selected_plan]
    db = get_supabase()

    # Calculate final amount (reuse logic)
    calc_body = {"selected_plan": selected_plan, "promo_code": promo_code}
    # Inline calculation
    base_price = plan_info["price"]
    new_limit = plan_info["student_limit"]

    count_result = (
        db.table("users")
        .select("id", count="exact")
        .eq("tenant_id", tenant_id)
        .eq("role", "student")
        .eq("is_active", True)
        .execute()
    )
    active_students = count_result.count if count_result.count is not None else 0

    overage_charge = 0
    if active_students > new_limit:
        overage_charge = (active_students - new_limit) * OVERAGE_RATE

    discount = 0
    if promo_code:
        promo = db.table("promo_codes").select("*").eq("code", promo_code).eq("is_active", True).maybe_single().execute()
        if promo.data:
            p = promo.data
            if p["discount_type"] == "percentage":
                discount = (base_price + overage_charge) * (p["discount_value"] / 100)
            else:
                discount = min(p["discount_value"], base_price + overage_charge)
            # Increment usage
            db.table("promo_codes").update({"current_uses": (p.get("current_uses", 0) or 0) + 1}).eq("id", p["id"]).execute()

    final_amount = max(0, base_price + overage_charge - discount)
    payment_status = "waived" if final_amount == 0 else "paid"

    now = datetime.now(timezone.utc)
    cycle_start = now.date()
    cycle_end = (now + timedelta(days=plan_info["duration_days"])).date()

    # Create billing record
    db.table("tenant_billing").insert({
        "tenant_id": tenant_id,
        "plan": selected_plan,
        "base_price": base_price,
        "overage_charge": overage_charge,
        "discount_applied": round(discount, 2),
        "final_amount": round(final_amount, 2),
        "promo_code_used": promo_code if promo_code else None,
        "billing_cycle_start": str(cycle_start),
        "billing_cycle_end": str(cycle_end),
        "payment_status": payment_status,
    }).execute()

    # Update tenant
    db.table("tenants").update({
        "subscription_plan": selected_plan,
        "max_students": new_limit,
        "student_limit": new_limit,
        "is_active": True,
    }).eq("id", tenant_id).execute()

    return success_response(
        data={
            "plan": selected_plan,
            "final_amount": round(final_amount, 2),
            "payment_status": payment_status,
            "billing_cycle_start": str(cycle_start),
            "billing_cycle_end": str(cycle_end),
        },
        message=f"Subscription activated: {plan_info['label']} plan!",
    )


@router.get("/history")
async def billing_history(user: dict = Depends(require_role(["admin", "super_admin"]))):
    """Get billing history for tenant."""
    tenant_id = user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant associated")

    db = get_supabase()
    result = (
        db.table("tenant_billing")
        .select("*")
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )

    return success_response(data=result.data)
