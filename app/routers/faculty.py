"""
Faculty router — Attendance, Marks submission, OD faculty-level approval.
All queries use user_id from Supabase (not Firebase UID).
"""

from fastapi import APIRouter, Depends, HTTPException
from app.core.security import require_role
from app.core.middleware import get_tenant_id
from app.core.database import get_supabase
from app.schemas.workflow import AttendanceMark, MarksSubmit, ODAction
from app.utils.response import success_response
from datetime import datetime

router = APIRouter(prefix="/api/faculty", tags=["Faculty"])


# ===== ATTENDANCE =====

@router.post("/attendance/mark")
async def mark_attendance(
    body: AttendanceMark,
    user: dict = Depends(require_role(["faculty"])),
):
    """Mark attendance for a session. Bulk insert for all students."""
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    user_id = user.get("user_id", user.get("uid"))

    records = []
    for rec in body.records:
        records.append({
            "tenant_id": tenant_id,
            "subject_id": body.subject_id,
            "student_id": rec.student_id,
            "faculty_id": user_id,
            "date": body.date.isoformat(),
            "session": body.session,
            "status": rec.status,
            "created_by": user_id,
        })

    result = db.table("attendance").insert(records).execute()
    return success_response(
        data={"count": len(result.data)},
        message=f"Attendance marked for {len(result.data)} students",
    )


@router.get("/attendance/{subject_id}")
async def get_attendance(
    subject_id: str,
    user: dict = Depends(require_role(["faculty", "hod", "admin"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    result = (
        db.table("attendance")
        .select("*, users!attendance_student_id_fkey(name, email)")
        .eq("tenant_id", tenant_id)
        .eq("subject_id", subject_id)
        .order("date", desc=True)
        .execute()
    )
    return success_response(data=result.data)


@router.get("/my-subjects")
async def get_my_subjects(
    user: dict = Depends(require_role(["faculty"])),
):
    """Get subjects assigned to this faculty member."""
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    user_id = user.get("user_id", user.get("uid"))

    result = (
        db.table("faculty_assignments")
        .select("*, subjects(id, name, code, max_marks), batches(name, code)")
        .eq("tenant_id", tenant_id)
        .eq("faculty_id", user_id)
        .execute()
    )
    return success_response(data=result.data)

@router.get("/dashboard-stats")
async def get_dashboard_stats(
    user: dict = Depends(require_role(["faculty"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    user_id = user.get("user_id", user.get("uid"))

    # 1. Assigned subjects count
    assignments = db.table("faculty_assignments").select("id", count="exact").eq("tenant_id", tenant_id).eq("faculty_id", user_id).execute()
    subjects_count = getattr(assignments, "count", len(assignments.data)) if hasattr(assignments, "data") else 0
    
    # 2. Pending OD requests count
    students = db.table("batch_students").select("student_id").eq("tenant_id", tenant_id).eq("faculty_advisor_id", user_id).execute()
    student_ids = [s["student_id"] for s in students.data] if hasattr(students, "data") else []
    
    pending_od_count = 0
    if student_ids:
        od_req = db.table("od_requests").select("id", count="exact").eq("tenant_id", tenant_id).eq("status", "pending_faculty").in_("student_id", student_ids).execute()
        pending_od_count = getattr(od_req, "count", len(od_req.data)) if hasattr(od_req, "data") else 0

    # 3. Active assignments count
    active_assignments = db.table("assignments").select("id", count="exact").eq("tenant_id", tenant_id).eq("faculty_id", user_id).gte("due_date", datetime.utcnow().isoformat()).execute()
    active_assignments_count = getattr(active_assignments, "count", len(active_assignments.data)) if hasattr(active_assignments, "data") else 0

    return success_response(data={
        "subjects": subjects_count,
        "pending_od": pending_od_count,
        "active_assignments": active_assignments_count,
        "fa_students": len(student_ids)
    })


@router.get("/assignment-students/{assignment_id}")
async def get_assignment_students(
    assignment_id: str,
    user: dict = Depends(require_role(["faculty", "hod", "admin"])),
):
    """Get students enrolled in a specific batch that this faculty is assigned to."""
    db = get_supabase()
    tenant_id = get_tenant_id(user)

    # 1. Look up the faculty assignment to find the batch_id
    assignment = (
        db.table("faculty_assignments")
        .select("batch_id, subject_id")
        .eq("id", assignment_id)
        .eq("tenant_id", tenant_id)
        .maybe_single()
        .execute()
    )
    
    if not assignment.data or not assignment.data.get("batch_id"):
        raise HTTPException(status_code=404, detail="Assignment not found or no batch firmly linked")

    batch_id = assignment.data["batch_id"]

    # 2. Fetch the students enrolled into this specific batch
    batch_students = (
        db.table("batch_students")
        .select("*, users!batch_students_student_id_fkey(id, name, email)")
        .eq("tenant_id", tenant_id)
        .eq("batch_id", batch_id)
        .execute()
    )

    # Format it identically to how the frontend expects (previously from student_enrollments)
    # The frontend expects {id, name, email} nested under 'users'. In batch_students, the foreign key alias we just used is 'users'.
    return success_response(data=batch_students.data)


# ===== MARKS =====

@router.post("/marks/submit")
async def submit_marks(
    body: MarksSubmit,
    user: dict = Depends(require_role(["faculty"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    user_id = user.get("user_id", user.get("uid"))

    records = []
    for entry in body.entries:
        records.append({
            "tenant_id": tenant_id,
            "subject_id": body.subject_id,
            "student_id": entry.student_id,
            "marks": entry.marks,
            "max_marks": entry.max_marks,
            "status": "submitted",
            "submitted_by": user_id,
        })

    result = db.table("internal_marks").upsert(
        records,
        on_conflict="tenant_id,subject_id,student_id",
    ).execute()

    return success_response(
        data={"count": len(result.data)},
        message=f"Marks submitted for {len(result.data)} students",
    )


@router.get("/marks/{subject_id}")
async def get_marks(
    subject_id: str,
    user: dict = Depends(require_role(["faculty", "hod", "admin"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    result = (
        db.table("internal_marks")
        .select("*, users!internal_marks_student_id_fkey(name, email)")
        .eq("tenant_id", tenant_id)
        .eq("subject_id", subject_id)
        .execute()
    )
    return success_response(data=result.data)


# ===== OD APPROVAL (Faculty Level) =====

@router.get("/od/pending")
async def get_pending_od(
    user: dict = Depends(require_role(["faculty"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    user_id = user.get("user_id", user.get("uid"))

    # Get students assigned to this faculty as their Faculty Advisor
    students = (
        db.table("batch_students")
        .select("student_id")
        .eq("tenant_id", tenant_id)
        .eq("faculty_advisor_id", user_id)
        .execute()
    )
    student_ids = [s["student_id"] for s in students.data]

    if not student_ids:
        return success_response(data=[])

    result = (
        db.table("od_requests")
        .select("*, users!od_requests_student_id_fkey(name, email), subjects(name, code)")
        .eq("tenant_id", tenant_id)
        .eq("status", "pending_faculty")
        .in_("student_id", student_ids)
        .order("created_at", desc=True)
        .execute()
    )
    return success_response(data=result.data)


@router.patch("/od/{od_id}/action")
async def faculty_od_action(
    od_id: str,
    body: ODAction,
    user: dict = Depends(require_role(["faculty"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    user_id = user.get("user_id", user.get("uid"))
    now = datetime.utcnow().isoformat()

    if body.action == "approve":
        update_data = {
            "status": "pending_hod",
            "faculty_action_by": user_id,
            "faculty_action_at": now,
        }
    elif body.action == "reject":
        update_data = {
            "status": "rejected",
            "faculty_action_by": user_id,
            "faculty_action_at": now,
            "rejection_reason": body.rejection_reason,
        }
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

    result = (
        db.table("od_requests")
        .update(update_data)
        .eq("id", od_id)
        .eq("tenant_id", tenant_id)
        .eq("status", "pending_faculty")
        .execute()
    )
    return success_response(data=result.data, message=f"OD {body.action}d by faculty")
