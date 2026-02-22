"""
Assessments router — Manage dynamic Internal & External exams and grades.
"""

from fastapi import APIRouter, Depends, HTTPException
from app.core.security import require_role
from app.core.middleware import get_tenant_id
from app.core.database import get_supabase
from app.utils.response import success_response
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter(prefix="/api/admin/assessments", tags=["Admin Assessments"])

class ExamCreate(BaseModel):
    batch_id: str
    name: str
    exam_type: str = "internal" # internal, external
    max_marks: int = 100

class ExamUpdate(BaseModel):
    name: Optional[str] = None
    exam_type: Optional[str] = None
    max_marks: Optional[int] = None

class ExamMarkEntry(BaseModel):
    subject_id: str
    student_id: str
    marks: float

class ExamMarkSubmit(BaseModel):
    entries: List[ExamMarkEntry]

@router.post("/exams")
async def create_exam(
    body: ExamCreate,
    user: dict = Depends(require_role(["admin", "super_admin"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    
    data = {
        "tenant_id": tenant_id,
        "batch_id": body.batch_id,
        "name": body.name,
        "exam_type": body.exam_type,
        "max_marks": body.max_marks
    }
    
    result = db.table("exams").insert(data).execute()
    return success_response(data=result.data, message="Exam assessment created")

@router.get("/exams/{batch_id}")
async def get_exams(
    batch_id: str,
    user: dict = Depends(require_role(["admin", "super_admin", "faculty", "student"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    
    result = (
        db.table("exams")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("batch_id", batch_id)
        .order("created_at")
        .execute()
    )
    return success_response(data=result.data)

@router.delete("/exams/{exam_id}")
async def delete_exam(
    exam_id: str,
    user: dict = Depends(require_role(["admin", "super_admin"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    db.table("exams").delete().eq("tenant_id", tenant_id).eq("id", exam_id).execute()
    return success_response(message="Exam assessment deleted")

@router.post("/exams/{exam_id}/marks")
async def submit_external_marks(
    exam_id: str,
    body: ExamMarkSubmit,
    user: dict = Depends(require_role(["admin", "super_admin", "faculty"])),
):
    """Submit marks for ANY exam type (Internal or External)."""
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    user_id = user.get("user_id", user.get("uid"))
    
    # Optional logic: we could verify here if exam_type == external
    
    records = []
    for entry in body.entries:
        records.append({
            "tenant_id": tenant_id,
            "exam_id": exam_id,
            "subject_id": entry.subject_id,
            "student_id": entry.student_id,
            "marks": entry.marks,
            "updated_by": user_id
        })
        
    result = db.table("exam_marks").upsert(
        records, on_conflict="tenant_id,exam_id,subject_id,student_id"
    ).execute()
    
    return success_response(message=f"Marks uploaded for {len(records)} students")

@router.get("/exams/{exam_id}/marks")
async def get_exam_marks(
    exam_id: str,
    subject_id: Optional[str] = None,
    user: dict = Depends(require_role(["admin", "super_admin", "faculty"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    
    query = (
        db.table("exam_marks")
        .select("*, users!student_id(name, email, roll_number)")
        .eq("tenant_id", tenant_id)
        .eq("exam_id", exam_id)
    )
    
    if subject_id:
        query = query.eq("subject_id", subject_id)
        
    result = query.execute()
    return success_response(data=result.data)
