from pydantic import BaseModel
from typing import Optional

class AssignmentCreate(BaseModel):
    batch_id: str
    subject_id: str
    title: str
    description: Optional[str] = None
    due_date: str
    max_score: int = 100

class SubmissionGrade(BaseModel):
    score: int
    feedback: Optional[str] = None

class AssignmentSubmit(BaseModel):
    file_url: Optional[str] = None
