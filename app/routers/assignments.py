from fastapi import APIRouter, Depends, HTTPException
from app.core.security import require_role
from app.core.middleware import get_tenant_id
from app.core.database import get_supabase
from app.schemas.assignments import AssignmentCreate, SubmissionGrade, AssignmentSubmit
from app.utils.response import success_response
from datetime import datetime
from dateutil import parser # Use dateutil for parsing ISO formats with Z safely

router = APIRouter(prefix="/api/assignments", tags=["Assignments"])

# Faculty endpoints
@router.post("")
async def create_assignment(
    body: AssignmentCreate,
    user: dict = Depends(require_role(["faculty"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    user_id = user.get("user_id", user.get("uid"))

    data = {
        "tenant_id": tenant_id,
        "faculty_id": user_id,
        **body.model_dump(),
    }
    result = db.table("assignments").insert(data).execute()
    return success_response(data=result.data, message="Assignment created")

@router.get("/faculty")
async def get_faculty_assignments(
    user: dict = Depends(require_role(["faculty"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    user_id = user.get("user_id", user.get("uid"))

    result = (
        db.table("assignments")
        .select("*, batches(name, code), subjects(name, code)")
        .eq("tenant_id", tenant_id)
        .eq("faculty_id", user_id)
        .order("due_date", desc=False)
        .execute()
    )
    return success_response(data=result.data)

@router.get("/{assignment_id}/submissions")
async def get_submissions(
    assignment_id: str,
    user: dict = Depends(require_role(["faculty", "student"])), # student might want to view their own submission
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    user_role = user.get("role", "")
    user_id = user.get("user_id", user.get("uid"))
    
    query = (
        db.table("assignment_submissions")
        .select("*, users!assignment_submissions_student_id_fkey(name)")
        .eq("tenant_id", tenant_id)
        .eq("assignment_id", assignment_id)
    )
    
    if user_role == "student":
        query = query.eq("student_id", user_id)
        
    result = query.execute()
    return success_response(data=result.data)

@router.patch("/submissions/{submission_id}/grade")
async def grade_submission(
    submission_id: str,
    body: SubmissionGrade,
    user: dict = Depends(require_role(["faculty"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    result = (
        db.table("assignment_submissions")
        .update({
            "score": body.score,
            "feedback": body.feedback,
            "status": "graded"
        })
        .eq("id", submission_id)
        .eq("tenant_id", tenant_id)
        .execute()
    )
    return success_response(data=result.data, message="Submission graded")

# Student endpoints
@router.get("/student")
async def get_student_assignments(
    user: dict = Depends(require_role(["student"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    user_id = user.get("user_id", user.get("uid"))

    # Get student's batch
    student_batch = (
        db.table("batch_students")
        .select("batch_id")
        .eq("tenant_id", tenant_id)
        .eq("student_id", user_id)
        .maybe_single()
        .execute()
    )
    
    if not student_batch.data:
        return success_response(data=[])

    batch_id = student_batch.data["batch_id"]

    # Get assignments for this batch
    assignments = (
        db.table("assignments")
        .select("*, subjects(name, code), users!assignments_faculty_id_fkey(name)")
        .eq("tenant_id", tenant_id)
        .eq("batch_id", batch_id)
        .order("due_date", desc=False)
        .execute()
    )

    # Get student's submissions
    submissions = (
        db.table("assignment_submissions")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("student_id", user_id)
        .execute()
    )
    
    sub_map = {s["assignment_id"]: s for s in submissions.data}
    
    result = []
    for a in assignments.data:
        a["submission"] = sub_map.get(a["id"])
        result.append(a)

    return success_response(data=result)

@router.post("/{assignment_id}/submit")
async def submit_assignment(
    assignment_id: str,
    body: AssignmentSubmit,
    user: dict = Depends(require_role(["student"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    user_id = user.get("user_id", user.get("uid"))

    # check if assignment exists
    assignment = db.table("assignments").select("due_date").eq("id", assignment_id).maybe_single().execute()
    if not assignment.data:
        raise HTTPException(status_code=404, detail="Assignment not found")

    statusStr = "submitted"
    try:
        due_date = parser.isoparse(assignment.data["due_date"])
        if datetime.now(due_date.tzinfo) > due_date:
            statusStr = "late"
    except Exception:
        pass # fallback to submitted if parsing fails

    data = {
        "tenant_id": tenant_id,
        "assignment_id": assignment_id,
        "student_id": user_id,
        "file_url": body.file_url,
        "status": statusStr,
    }
    
    # Check if a submission already exists to decide between insert/update
    existing = db.table("assignment_submissions").select("id").eq("assignment_id", assignment_id).eq("student_id", user_id).maybe_single().execute()
    
    if existing.data:
        result = db.table("assignment_submissions").update(data).eq("id", existing.data["id"]).execute()
    else:
        result = db.table("assignment_submissions").insert(data).execute()
        
    return success_response(data=result.data, message="Assignment submitted")
