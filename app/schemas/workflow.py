"""
Pydantic schemas for attendance, marks, and OD workflows.
"""

from pydantic import BaseModel
from typing import Optional, List
from datetime import date


# ---- Attendance ----
class AttendanceRecord(BaseModel):
    student_id: str
    status: str  # present, absent, od


class AttendanceMark(BaseModel):
    subject_id: str
    date: date
    session: str = "morning"
    records: List[AttendanceRecord]


# ---- Internal Marks ----
class MarkEntry(BaseModel):
    student_id: str
    marks: float
    max_marks: int = 100


class MarksSubmit(BaseModel):
    subject_id: str
    entries: List[MarkEntry]


class MarksAction(BaseModel):
    action: str  # approve, reject


# ---- OD Request ----
class ODApply(BaseModel):
    subject_id: str
    date: date
    end_date: Optional[date] = None
    reason: str
    od_type: str = "normal" # normal, special, medical
    document_url: Optional[str] = None


class ODAction(BaseModel):
    action: str  # approve, reject
    rejection_reason: Optional[str] = None
