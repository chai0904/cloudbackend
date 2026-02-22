"""
HOD router — Approve marks, approve OD (HOD level), department stats.
"""

from fastapi import APIRouter, Depends, HTTPException
from app.core.security import require_role
from app.core.middleware import get_tenant_id
from app.core.database import get_supabase
from app.schemas.workflow import MarksAction, ODAction
from app.utils.response import success_response
from datetime import datetime

router = APIRouter(prefix="/api/hod", tags=["HOD"])


@router.get("/marks/pending")
async def get_pending_marks(
    user: dict = Depends(require_role(["hod", "admin"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    result = (
        db.table("internal_marks")
        .select("*, users!internal_marks_student_id_fkey(name, email), subjects(name, code)")
        .eq("tenant_id", tenant_id)
        .eq("status", "submitted")
        .order("created_at", desc=True)
        .execute()
    )
    return success_response(data=result.data)


@router.patch("/marks/{subject_id}/action")
async def approve_marks(
    subject_id: str,
    body: MarksAction,
    user: dict = Depends(require_role(["hod", "admin"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    user_id = user.get("user_id", user.get("uid"))
    now = datetime.utcnow().isoformat()

    if body.action == "approve":
        update_data = {
            "status": "approved",
            "approved_by": user_id,
            "approved_at": now,
        }
    elif body.action == "reject":
        update_data = {"status": "draft"}
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

    result = (
        db.table("internal_marks")
        .update(update_data)
        .eq("tenant_id", tenant_id)
        .eq("subject_id", subject_id)
        .eq("status", "submitted")
        .execute()
    )
    count = len(result.data) if result.data else 0
    return success_response(data=result.data, message=f"Marks {body.action}d ({count} entries)")


@router.get("/od/pending")
async def get_pending_od_hod(
    user: dict = Depends(require_role(["hod"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    result = (
        db.table("od_requests")
        .select("*, users!od_requests_student_id_fkey(name, email), subjects(name, code)")
        .eq("tenant_id", tenant_id)
        .eq("status", "pending_hod")
        .order("created_at", desc=True)
        .execute()
    )
    return success_response(data=result.data)


@router.patch("/od/{od_id}/action")
async def hod_od_action(
    od_id: str,
    body: ODAction,
    user: dict = Depends(require_role(["hod"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    user_id = user.get("user_id", user.get("uid"))
    now = datetime.utcnow().isoformat()

    if body.action == "approve":
        update_data = {
            "status": "approved",
            "hod_action_by": user_id,
            "hod_action_at": now,
        }
    elif body.action == "reject":
        update_data = {
            "status": "rejected",
            "hod_action_by": user_id,
            "hod_action_at": now,
            "rejection_reason": body.rejection_reason,
        }
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

    result = (
        db.table("od_requests")
        .update(update_data)
        .eq("id", od_id)
        .eq("tenant_id", tenant_id)
        .eq("status", "pending_hod")
        .execute()
    )
    return success_response(data=result.data, message=f"OD {body.action}d by HOD")


@router.get("/department/stats")
async def department_stats(
    user: dict = Depends(require_role(["hod", "admin"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)

    attendance = (
        db.table("attendance")
        .select("student_id, status, users!attendance_student_id_fkey(name, email)")
        .eq("tenant_id", tenant_id)
        .execute()
    )

    student_stats = {}
    for rec in attendance.data:
        sid = rec["student_id"]
        student_info = rec.get("users", {})
        if sid not in student_stats:
            student_stats[sid] = {
                "total": 0, "present": 0,
                "name": student_info.get("name", sid),
                "email": student_info.get("email", ""),
            }
        student_stats[sid]["total"] += 1
        if rec["status"] in ("present", "od"):
            student_stats[sid]["present"] += 1

    defaulters = []
    for sid, stats in student_stats.items():
        pct = (stats["present"] / stats["total"] * 100) if stats["total"] > 0 else 0
        if pct < 75:
            defaulters.append({
                "student_id": sid,
                "name": stats["name"],
                "email": stats["email"],
                "attendance_percentage": round(pct, 2),
                "total_sessions": stats["total"],
                "present": stats["present"],
            })

    total_students = len(student_stats)

    faculty_req = db.table("users").select("id", count="exact").eq("tenant_id", tenant_id).eq("role", "faculty").execute()
    total_faculty = getattr(faculty_req, "count", len(faculty_req.data)) if hasattr(faculty_req, "data") else 0

    marks_req = db.table("internal_marks").select("id", count="exact").eq("tenant_id", tenant_id).eq("status", "submitted").execute()
    pending_marks = getattr(marks_req, "count", len(marks_req.data)) if hasattr(marks_req, "data") else 0

    return success_response(data={
        "defaulters": defaulters,
        "total_students": total_students,
        "total_faculty": total_faculty,
        "pending_marks": pending_marks,
    })
