"""
Pydantic schemas for academic structure management.
"""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# ---- Tenant ----
class TenantCreate(BaseModel):
    name: str
    code: str
    subscription_plan: str = "starter"


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    subscription_plan: Optional[str] = None
    is_active: Optional[bool] = None


class TenantResponse(BaseModel):
    id: str
    name: str
    code: str
    subscription_plan: str
    is_active: bool


# ---- Department ----
class DepartmentCreate(BaseModel):
    name: str
    code: str
    hod_id: Optional[str] = None


class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    hod_id: Optional[str] = None


# ---- Academic Year ----
class AcademicYearCreate(BaseModel):
    year_label: str
    is_current: bool = False


# ---- Program ----
class ProgramCreate(BaseModel):
    department_id: str
    name: str
    code: str
    duration_years: int = 4


# ---- Semester ----
class SemesterCreate(BaseModel):
    academic_year_id: str
    program_id: str
    semester_number: int
    is_active: bool = True


# ---- Subject ----
class SubjectCreate(BaseModel):
    semester: int
    program_id: str
    name: str
    code: str
    max_marks: int = 100


# ---- Faculty Assignment ----
class FacultyAssignmentCreate(BaseModel):
    faculty_id: str
    subject_id: str


# ---- Student Enrollment ----
class StudentEnrollmentCreate(BaseModel):
    student_id: str
    program_id: str
    semester_id: str
    roll_number: Optional[str] = None
