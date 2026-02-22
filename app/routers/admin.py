"""
Admin router — Tenant management (Super Admin) + Academic structure & User management (Institution Admin).

Institution Admin can:
- Create internal users (faculty, hod, students)
- Assign roles & departments
- Activate/deactivate users
- Manage academic structure (departments, programs, semesters, subjects)
- Assign faculty, enroll students
- Lock marks, generate reports
"""

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from app.core.security import require_role, get_current_user, settings, get_password_hash
from app.core.middleware import get_tenant_id
from app.core.database import get_supabase
from app.schemas.academic import (
    TenantCreate, TenantUpdate, DepartmentCreate, DepartmentUpdate,
    AcademicYearCreate, ProgramCreate, SemesterCreate, SubjectCreate,
    FacultyAssignmentCreate, StudentEnrollmentCreate,
)
from app.utils.response import success_response
from datetime import datetime

router = APIRouter(prefix="/api/admin", tags=["Admin"])


# ═══════════════════════════════════════════════════════════
# TENANT MANAGEMENT (Super Admin only)
# ═══════════════════════════════════════════════════════════

@router.post("/tenants")
async def create_tenant(
    body: TenantCreate,
    user: dict = Depends(require_role(["super_admin"])),
):
    db = get_supabase()
    data = body.model_dump()
    data["subscription_plan"] = data.get("subscription_plan", "trial")
    result = db.table("tenants").insert(data).execute()
    return success_response(data=result.data, message="Tenant created")


@router.get("/tenants")
async def list_tenants(user: dict = Depends(require_role(["super_admin"]))):
    db = get_supabase()
    result = db.table("tenants").select("*").order("created_at", desc=True).execute()
    return success_response(data=result.data)


@router.patch("/tenants/{tenant_id}")
async def update_tenant(
    tenant_id: str,
    body: TenantUpdate,
    user: dict = Depends(require_role(["super_admin"])),
):
    db = get_supabase()
    update_data = {k: v for k, v in body.model_dump().items() if v is not None}
    result = db.table("tenants").update(update_data).eq("id", tenant_id).execute()
    return success_response(data=result.data, message="Tenant updated")


# ═══════════════════════════════════════════════════════════
# INSTITUTIONAL USER MANAGEMENT (Admin creates all users)
# ═══════════════════════════════════════════════════════════

@router.post("/users")
async def create_user(
    body: dict,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_role(["admin", "super_admin"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)

    email = body.get("email")
    name = body.get("name")
    role = body.get("role")

    # Enforce subscription limits for student creation
    if role == "student" and tenant_id:
        from app.core.subscription import check_subscription, check_student_limit
        check_subscription(tenant_id)
        check_student_limit(tenant_id)

    department_id = body.get("department_id")
    
    import secrets
    import string
    # Generate a random 8-character password if not provided
    password = body.get("password")
    if not password:
        alphabet = string.ascii_letters + string.digits
        password = ''.join(secrets.choice(alphabet) for _ in range(8))

    if not all([email, name, role]):
        raise HTTPException(status_code=400, detail="email, name, and role are required")

    if role not in ("admin", "hod", "faculty", "student"):
        raise HTTPException(status_code=400, detail="Invalid role. Must be: admin, hod, faculty, student")

    # Check if email already exists
    existing = db.table("users").select("id").eq("email", email).maybe_single().execute()
    if existing and existing.data:
        raise HTTPException(status_code=400, detail=f"User with email '{email}' already exists")

    firebase_uid = f"mock-{email}"

    # In Firebase mode, create the Firebase user too
    if settings.AUTH_MODE == "firebase":
        try:
            from firebase_admin import auth as fb_auth
            fb_user = fb_auth.create_user(
                email=email,
                password=password,
                display_name=name,
            )
            firebase_uid = fb_user.uid
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Firebase user creation failed: {str(e)}")

    department_id = department_id if department_id and department_id.strip() else None

    user_data = {
        "tenant_id": tenant_id if tenant_id and tenant_id.strip() else None,
        "email": email,
        "name": name,
        "role": role,
        "department_id": department_id,
        "firebase_uid": firebase_uid,
        "is_active": True,
        "password_hash": get_password_hash(password),
        "requires_password_reset": True,
    }

    result = db.table("users").insert(user_data).execute()
    created_user = result.data[0] if result.data else None

    # Auto-assign student to a batch if specified
    if created_user and role == "student":
        batch_id = body.get("batch_id")
        if batch_id and str(batch_id).strip():
            try:
                db.table("batch_students").insert({
                    "tenant_id": tenant_id if tenant_id and tenant_id.strip() else None,
                    "batch_id": str(batch_id).strip(),
                    "student_id": created_user["id"]
                }).execute()
            except Exception as e:
                print(f"Failed to auto-assign student to batch: {e}")

    # Trigger welcome email in the background
    from app.core.email import send_welcome_email
    
    # Try to fetch tenant name if available, otherwise just use 'Your Institution'
    org_name = "Your Institution"
    if tenant_id:
        try:
            t_data = db.table("tenants").select("name").eq("id", tenant_id).execute()
            if t_data.data:
                org_name = t_data.data[0]["name"]
        except Exception:
            pass

    # Return the generated password and org name so the frontend can send the EmailJS welcome email directly
    return success_response(
        data={
            "user": created_user,
            "temp_password": password,
            "org_name": org_name,
            "mock_token": f"mock-{email}" if settings.AUTH_MODE == "mock" else None,
        },
        message=f"User '{name}' ({role}) created successfully",
    )


@router.get("/users")
async def list_users(user: dict = Depends(require_role(["admin", "super_admin"]))):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    query = db.table("users").select("*").order("role").order("name")
    if tenant_id:
        query = query.eq("tenant_id", tenant_id)
    result = query.execute()
    return success_response(data=result.data)


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    body: dict,
    user: dict = Depends(require_role(["admin"])),
):
    """Update user details. Admin can activate/deactivate, change role, assign department."""
    db = get_supabase()
    tenant_id = get_tenant_id(user)

    allowed_fields = {"name", "role", "department_id", "is_active"}
    update_data = {k: v for k, v in body.items() if k in allowed_fields and v is not None}

    if not update_data:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    result = (
        db.table("users")
        .update(update_data)
        .eq("id", user_id)
        .eq("tenant_id", tenant_id)
        .execute()
    )
    return success_response(data=result.data, message="User updated")


@router.delete("/users/{user_id}")
async def deactivate_user(
    user_id: str,
    user: dict = Depends(require_role(["admin"])),
):
    """Deactivate a user (soft delete — set is_active=false)."""
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    result = (
        db.table("users")
        .update({"is_active": False})
        .eq("id", user_id)
        .eq("tenant_id", tenant_id)
        .execute()
    )
    return success_response(data=result.data, message="User deactivated")


# ═══════════════════════════════════════════════════════════
# DEPARTMENTS
# ═══════════════════════════════════════════════════════════

@router.post("/departments")
async def create_department(
    body: DepartmentCreate,
    user: dict = Depends(require_role(["admin"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    data = {**body.model_dump(), "tenant_id": tenant_id}
    result = db.table("departments").insert(data).execute()
    return success_response(data=result.data, message="Department created")


@router.get("/departments")
async def list_departments(user: dict = Depends(require_role(["admin", "hod", "faculty"]))):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    result = db.table("departments").select("*").eq("tenant_id", tenant_id).order("name").execute()
    return success_response(data=result.data)


@router.patch("/departments/{dept_id}")
async def update_department(
    dept_id: str,
    body: DepartmentUpdate,
    user: dict = Depends(require_role(["admin"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    update_data = {k: v for k, v in body.model_dump().items() if v is not None}
    result = (
        db.table("departments")
        .update(update_data)
        .eq("id", dept_id)
        .eq("tenant_id", tenant_id)
        .execute()
    )
    return success_response(data=result.data, message="Department updated")


# ═══════════════════════════════════════════════════════════
# ACADEMIC YEARS
# ═══════════════════════════════════════════════════════════

@router.post("/academic-years")
async def create_academic_year(
    body: AcademicYearCreate,
    user: dict = Depends(require_role(["admin"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    data = {**body.model_dump(), "tenant_id": tenant_id}
    result = db.table("academic_years").insert(data).execute()
    return success_response(data=result.data, message="Academic year created")


@router.get("/academic-years")
async def list_academic_years(user: dict = Depends(require_role(["admin", "hod", "faculty"]))):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    result = db.table("academic_years").select("*").eq("tenant_id", tenant_id).order("year_label", desc=True).execute()
    return success_response(data=result.data)


# ═══════════════════════════════════════════════════════════
# PROGRAMS
# ═══════════════════════════════════════════════════════════

@router.post("/programs")
async def create_program(
    body: ProgramCreate,
    user: dict = Depends(require_role(["admin"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    data = {**body.model_dump(), "tenant_id": tenant_id}
    result = db.table("programs").insert(data).execute()
    return success_response(data=result.data, message="Program created")


@router.get("/programs")
async def list_programs(user: dict = Depends(require_role(["admin", "hod", "faculty"]))):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    result = db.table("programs").select("*, departments(name)").eq("tenant_id", tenant_id).order("name").execute()
    return success_response(data=result.data)


# ═══════════════════════════════════════════════════════════
# SEMESTERS
# ═══════════════════════════════════════════════════════════

@router.post("/semesters")
async def create_semester(
    body: SemesterCreate,
    user: dict = Depends(require_role(["admin"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    data = {**body.model_dump(), "tenant_id": tenant_id}
    result = db.table("semesters").insert(data).execute()
    return success_response(data=result.data, message="Semester created")


@router.get("/semesters")
async def list_semesters(user: dict = Depends(require_role(["admin", "hod", "faculty"]))):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    result = (
        db.table("semesters")
        .select("*, academic_years(year_label), programs(name, code)")
        .eq("tenant_id", tenant_id)
        .order("semester_number")
        .execute()
    )
    return success_response(data=result.data)


# ═══════════════════════════════════════════════════════════
# SUBJECTS
# ═══════════════════════════════════════════════════════════

@router.post("/subjects")
async def create_subject(
    body: SubjectCreate,
    user: dict = Depends(require_role(["admin"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    data = {**body.model_dump(), "tenant_id": tenant_id}
    result = db.table("subjects").insert(data).execute()
    return success_response(data=result.data, message="Subject created")


@router.get("/subjects")
async def list_subjects(user: dict = Depends(require_role(["admin", "hod", "faculty"]))):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    result = (
        db.table("subjects")
        .select("*, programs(name, code)")
        .eq("tenant_id", tenant_id)
        .order("code")
        .execute()
    )
    return success_response(data=result.data)


# ═══════════════════════════════════════════════════════════
# FACULTY ASSIGNMENTS
# ═══════════════════════════════════════════════════════════

@router.post("/faculty-assignments")
async def assign_faculty(
    body: FacultyAssignmentCreate,
    user: dict = Depends(require_role(["admin"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    data = {**body.model_dump(), "tenant_id": tenant_id}
    result = db.table("faculty_assignments").insert(data).execute()
    return success_response(data=result.data, message="Faculty assigned")


@router.get("/faculty-assignments")
async def list_faculty_assignments(user: dict = Depends(require_role(["admin", "hod"]))):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    result = (
        db.table("faculty_assignments")
        .select("*, users!faculty_assignments_faculty_id_fkey(name, email), subjects(name, code)")
        .eq("tenant_id", tenant_id)
        .execute()
    )
    return success_response(data=result.data)


# ═══════════════════════════════════════════════════════════
# STUDENT ENROLLMENTS
# ═══════════════════════════════════════════════════════════

@router.post("/student-enrollments")
async def enroll_student(
    body: StudentEnrollmentCreate,
    user: dict = Depends(require_role(["admin"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    data = {**body.model_dump(), "tenant_id": tenant_id}
    result = db.table("student_enrollments").insert(data).execute()
    return success_response(data=result.data, message="Student enrolled")


@router.get("/student-enrollments")
async def list_enrollments(user: dict = Depends(require_role(["admin", "hod"]))):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    result = (
        db.table("student_enrollments")
        .select("*, users!student_enrollments_student_id_fkey(name, email, role)")
        .eq("tenant_id", tenant_id)
        .execute()
    )
    return success_response(data=result.data)


# ═══════════════════════════════════════════════════════════
# LOCK MARKS
# ═══════════════════════════════════════════════════════════

@router.post("/marks/lock/{subject_id}")
async def lock_marks(
    subject_id: str,
    user: dict = Depends(require_role(["admin"])),
):
    """Lock all approved marks for a subject. Irreversible — students can see after."""
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    now = datetime.utcnow().isoformat()
    result = (
        db.table("internal_marks")
        .update({
            "status": "locked",
            "locked_by": user.get("user_id", user.get("uid")),
            "locked_at": now,
        })
        .eq("tenant_id", tenant_id)
        .eq("subject_id", subject_id)
        .eq("status", "approved")
        .execute()
    )
    count = len(result.data) if result.data else 0
    return success_response(data=result.data, message=f"Locked {count} mark entries")
