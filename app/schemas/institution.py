"""
Pydantic schemas for institutional management:
Batches, Classrooms, Bulk Import, Faculty Workload, Timetable.
"""

from pydantic import BaseModel
from typing import Optional, List


# ---- Batches / Sections ----
class BatchCreate(BaseModel):
    program_id: str
    semester: int
    name: str
    code: str
    max_students: int = 60
    academic_year_id: Optional[str] = None


class BatchStudentAdd(BaseModel):
    batch_id: str
    student_id: str
    roll_number: Optional[str] = None


class BatchStudentBulk(BaseModel):
    batch_id: str
    students: List[dict]  # [{student_id, roll_number}]


class BatchStudentFAAssign(BaseModel):
    batch_id: str
    faculty_advisor_id: Optional[str] = None
    student_ids: List[str]


# ---- Classrooms ----
class ClassroomCreate(BaseModel):
    name: str
    code: str
    building: Optional[str] = None
    floor: Optional[str] = None
    capacity: int = 60
    room_type: str = "lecture"


# ---- Bulk Import ----
class BulkStudentEntry(BaseModel):
    email: str
    name: str
    department_id: Optional[str] = None
    batch_code: Optional[str] = None
    roll_number: Optional[str] = None


class BulkFacultyEntry(BaseModel):
    email: str
    name: str
    department_id: Optional[str] = None
    max_hours_per_week: int = 20


class BulkImportStudents(BaseModel):
    students: List[BulkStudentEntry]


class BulkImportFaculty(BaseModel):
    faculty: List[BulkFacultyEntry]


# ---- Faculty Workload ----
class FacultyWorkloadUpdate(BaseModel):
    max_hours_per_week: int = 20
    preferred_slots: Optional[str] = None
    unavailable_slots: Optional[str] = None


class FacultyAssignmentExtended(BaseModel):
    faculty_id: str
    subject_id: str
    batch_id: Optional[str] = None
    hours_per_week: int = 4


# ---- Timetable ----
class TimetableSlotCreate(BaseModel):
    batch_id: str
    subject_id: str
    faculty_id: str
    classroom_id: Optional[str] = None
    day_of_week: int  # 1=Mon ... 6=Sat
    period_number: int
    start_time: str  # "09:00"
    end_time: str    # "09:50"
    slot_type: str = "lecture"


class TimetableGenerate(BaseModel):
    batch_id: str
    force_regenerate: bool = False


class PeriodTemplateCreate(BaseModel):
    period_number: int
    start_time: str
    end_time: str
    label: Optional[str] = None
    is_break: bool = False
