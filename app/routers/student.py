"""
Student router — View attendance, view marks, apply OD.
All queries use user_id (Supabase UUID) not Firebase UID.
"""

from fastapi import APIRouter, Depends, HTTPException
from app.core.security import require_role
from app.core.middleware import get_tenant_id
from app.core.database import get_supabase
from app.schemas.workflow import ODApply
from app.utils.response import success_response

router = APIRouter(prefix="/api/student", tags=["Student"])


@router.get("/attendance")
async def get_my_attendance(
    user: dict = Depends(require_role(["student"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    user_id = user.get("user_id", user.get("uid"))

    result = (
        db.table("attendance")
        .select("*, subjects(name, code)")
        .eq("tenant_id", tenant_id)
        .eq("student_id", user_id)
        .order("date", desc=True)
        .execute()
    )

    # Calculate per-subject percentage
    subject_stats = {}
    for rec in result.data:
        sid = rec["subject_id"]
        subject_info = rec.get("subjects", {})
        if sid not in subject_stats:
            subject_stats[sid] = {
                "total": 0, "present": 0,
                "subject_name": subject_info.get("name", ""),
                "subject_code": subject_info.get("code", ""),
            }
        subject_stats[sid]["total"] += 1
        if rec["status"] in ("present", "od"):
            subject_stats[sid]["present"] += 1

    summary = []
    for subject_id, stats in subject_stats.items():
        pct = (stats["present"] / stats["total"] * 100) if stats["total"] > 0 else 0
        summary.append({
            "subject_id": subject_id,
            "subject_name": stats["subject_name"],
            "subject_code": stats["subject_code"],
            "total_sessions": stats["total"],
            "present": stats["present"],
            "percentage": round(pct, 2),
            "flagged": pct < 75,
        })

    return success_response(data={
        "summary": summary,
        "records": result.data,
    })


@router.get("/marks")
async def get_my_marks(
    user: dict = Depends(require_role(["student"])),
):
    """Get internal marks AND new dynamic exams (FAT/End Sem)."""
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    user_id = user.get("user_id", user.get("uid"))

    # Legacy static internal marks
    internal_res = (
        db.table("internal_marks")
        .select("*, subjects(name, code)")
        .eq("tenant_id", tenant_id)
        .eq("student_id", user_id)
        .eq("status", "locked")
        .execute()
    )
    
    # New Dynamic Exam marks
    exams_res = (
        db.table("exam_marks")
        .select("*, subjects(name, code), exams(name, exam_type, max_marks)")
        .eq("tenant_id", tenant_id)
        .eq("student_id", user_id)
        .execute()
    )

    return success_response(data={
        "legacy_marks": internal_res.data,
        "dynamic_exams": exams_res.data
    })

@router.post("/od/apply")
async def apply_od(
    body: ODApply,
    user: dict = Depends(require_role(["student"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    user_id = user.get("user_id", user.get("uid"))

    # Validate and auto-fill subject_id if missing or empty string
    subject_id = body.subject_id
    if not subject_id:
        enrollments = (
            db.table("student_enrollments")
            .select("program_id, semesters!inner(semester_number)")
            .eq("tenant_id", tenant_id)
            .eq("student_id", user_id)
            .limit(1)
            .execute()
        )
        if enrollments.data:
            ext = enrollments.data[0]
            prog = ext.get("program_id")
            sem_num = ext.get("semesters", {}).get("semester_number")
            if prog and sem_num:
                subs = (
                    db.table("subjects")
                    .select("id")
                    .eq("tenant_id", tenant_id)
                    .eq("program_id", prog)
                    .eq("semester", sem_num)
                    .limit(1)
                    .execute()
                )
                if subs.data:
                    subject_id = subs.data[0]["id"]
        
        if not subject_id:
            any_sub = db.table("subjects").select("id").eq("tenant_id", tenant_id).limit(1).execute()
            if any_sub.data:
                subject_id = any_sub.data[0]["id"]
            else:
                raise HTTPException(status_code=400, detail="System Error: No subjects exist in the institution.")

    # Determine initial status based on OD type
    initial_status = "pending_hod" if body.od_type in ["special", "medical"] else "pending_faculty"

    data = {
        "tenant_id": tenant_id,
        "student_id": user_id,
        "subject_id": subject_id,
        "date": body.date.isoformat(),
        "end_date": body.end_date.isoformat() if body.end_date else None,
        "reason": body.reason,
        "od_type": body.od_type,
        "document_url": body.document_url,
        "status": initial_status,
    }
    result = db.table("od_requests").insert(data).execute()
    return success_response(data=result.data, message="OD request submitted")


@router.get("/od/status")
async def get_my_od_requests(
    user: dict = Depends(require_role(["student"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    user_id = user.get("user_id", user.get("uid"))

    result = (
        db.table("od_requests")
        .select("*, subjects(name, code)")
        .eq("tenant_id", tenant_id)
        .eq("student_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return success_response(data=result.data)


@router.get("/my-subjects")
async def get_my_subjects(
    user: dict = Depends(require_role(["student"])),
):
    """Get subjects the student is enrolled in."""
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    user_id = user.get("user_id", user.get("uid"))

    enrollments = (
        db.table("student_enrollments")
        .select("program_id, semesters!inner(semester_number)")
        .eq("tenant_id", tenant_id)
        .eq("student_id", user_id)
        .execute()
    )

    if not enrollments.data:
        return success_response(data=[])

    all_subjects = []
    for ext in enrollments.data:
        prog = ext.get("program_id")
        sem_num = ext.get("semesters", {}).get("semester_number")
        if prog and sem_num:
            subs = (
                db.table("subjects")
                .select("id, name, code, max_marks")
                .eq("tenant_id", tenant_id)
                .eq("program_id", prog)
                .eq("semester", sem_num)
                .order("code")
                .execute()
            )
            if subs.data:
                all_subjects.extend(subs.data)
                
    # remove duplicates if any
    unique_subjects = {s["id"]: s for s in all_subjects}.values()

    return success_response(data=list(unique_subjects))
