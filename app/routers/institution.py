"""
Institution Management router — Batches, Classrooms, Bulk Import, Faculty Workload, Timetable.
All endpoints for Institution Admin to set up their institution completely.
"""

from fastapi import APIRouter, Depends, HTTPException
from app.core.security import require_role, settings
from app.core.middleware import get_tenant_id
from app.core.database import get_supabase
from app.schemas.institution import (
    BatchCreate, ClassroomCreate, BulkImportStudents, BulkImportFaculty,
    FacultyAssignmentExtended, FacultyWorkloadUpdate,
    TimetableSlotCreate, TimetableGenerate, PeriodTemplateCreate,
)
from app.utils.response import success_response
import json

router = APIRouter(prefix="/api/institution", tags=["Institution Management"])


# ═══════════════════════════════════════════════════════════
# BATCHES / SECTIONS
# ═══════════════════════════════════════════════════════════

@router.post("/batches")
async def create_batch(
    body: BatchCreate,
    user: dict = Depends(require_role(["admin"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    data = {**body.model_dump(), "tenant_id": tenant_id}
    result = db.table("batches").insert(data).execute()
    return success_response(data=result.data, message="Batch created")


@router.get("/batches")
async def list_batches(user: dict = Depends(require_role(["admin", "hod", "faculty"]))):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    result = (
        db.table("batches")
        .select("*, programs(name, code)")
        .eq("tenant_id", tenant_id)
        .order("code")
        .execute()
    )
    return success_response(data=result.data)


@router.get("/batches/{batch_id}/students")
async def get_batch_students(
    batch_id: str,
    user: dict = Depends(require_role(["admin", "hod", "faculty"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    result = (
        db.table("batch_students")
        .select("*, students:users!batch_students_student_id_fkey(id, name, email), faculty_advisors:users!batch_students_faculty_advisor_id_fkey(id, name, email)")
        .eq("tenant_id", tenant_id)
        .eq("batch_id", batch_id)
        .order("roll_number")
        .execute()
    )
    return success_response(data=result.data)


@router.post("/batches/{batch_id}/students")
async def add_student_to_batch(
    batch_id: str,
    body: dict,
    user: dict = Depends(require_role(["admin"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    data = {
        "tenant_id": tenant_id,
        "batch_id": batch_id,
        "student_id": body.get("student_id"),
        "roll_number": body.get("roll_number"),
    }
    result = db.table("batch_students").insert(data).execute()
    return success_response(data=result.data, message="Student added to batch")


@router.post("/batches/{batch_id}/students/bulk")
async def bulk_add_students_to_batch(
    batch_id: str,
    body: dict,
    user: dict = Depends(require_role(["admin"])),
):
    """Add multiple students to a batch at once."""
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    students = body.get("students", [])

    records = [
        {
            "tenant_id": tenant_id,
            "batch_id": batch_id,
            "student_id": s.get("student_id"),
            "roll_number": s.get("roll_number"),
        }
        for s in students
    ]
    result = db.table("batch_students").insert(records).execute()
    return success_response(
        data={"count": len(result.data)},
        message=f"Added {len(result.data)} students to batch",
    )


@router.patch("/batches/{batch_id}/students/fa")
async def assign_faculty_advisor(
    batch_id: str,
    body: dict,
    user: dict = Depends(require_role(["admin", "hod"])),
):
    """Assign a faculty advisor to a list of students in a batch."""
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    
    faculty_advisor_id = body.get("faculty_advisor_id")
    student_ids = body.get("student_ids", [])
    
    if not student_ids:
        raise HTTPException(status_code=400, detail="No students selected")

    result = (
        db.table("batch_students")
        .update({"faculty_advisor_id": faculty_advisor_id})
        .eq("tenant_id", tenant_id)
        .eq("batch_id", batch_id)
        .in_("student_id", student_ids)
        .execute()
    )
    
    return success_response(
        data={"count": len(result.data)},
        message=f"Assigned FA to {len(result.data)} students",
    )


@router.get("/batches/{batch_id}/subjects")
async def get_batch_subjects(
    batch_id: str,
    user: dict = Depends(require_role(["admin", "hod", "faculty"])),
):
    """Fetch all subjects that belong to this batch's program and semester."""
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    
    batch = db.table("batches").select("program_id, semester").eq("tenant_id", tenant_id).eq("id", batch_id).maybe_single().execute()
    if not batch.data:
        raise HTTPException(status_code=404, detail="Batch not found")
        
    program_id = batch.data.get("program_id")
    semester = batch.data.get("semester")
    
    subjects = (
        db.table("subjects")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("program_id", program_id)
        .eq("semester", semester)
        .execute()
    )
    return success_response(data=subjects.data)


@router.delete("/batches/{batch_id}")
async def delete_batch(
    batch_id: str,
    user: dict = Depends(require_role(["admin"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    db.table("batches").delete().eq("id", batch_id).eq("tenant_id", tenant_id).execute()
    return success_response(message="Batch deleted")


# ═══════════════════════════════════════════════════════════
# CLASSROOMS / ROOMS
# ═══════════════════════════════════════════════════════════

@router.post("/classrooms")
async def create_classroom(
    body: ClassroomCreate,
    user: dict = Depends(require_role(["admin"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    data = {**body.model_dump(), "tenant_id": tenant_id}
    result = db.table("classrooms").insert(data).execute()
    return success_response(data=result.data, message="Classroom created")


@router.get("/classrooms")
async def list_classrooms(user: dict = Depends(require_role(["admin", "hod", "faculty"]))):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    result = (
        db.table("classrooms")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("is_available", True)
        .order("code")
        .execute()
    )
    return success_response(data=result.data)


@router.patch("/classrooms/{room_id}")
async def update_classroom(
    room_id: str,
    body: dict,
    user: dict = Depends(require_role(["admin"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    allowed = {"name", "code", "building", "floor", "capacity", "room_type", "is_available"}
    update_data = {k: v for k, v in body.items() if k in allowed}
    result = (
        db.table("classrooms")
        .update(update_data)
        .eq("id", room_id)
        .eq("tenant_id", tenant_id)
        .execute()
    )
    return success_response(data=result.data, message="Classroom updated")


# ═══════════════════════════════════════════════════════════
# BULK IMPORT — Students
# ═══════════════════════════════════════════════════════════

@router.post("/bulk/students")
async def bulk_import_students(
    body: BulkImportStudents,
    user: dict = Depends(require_role(["admin"])),
):
    """
    Bulk create student users.
    Each entry needs: email, name.
    Optional: department_id, batch_code, roll_number.
    """
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    creator_id = user.get("user_id")

    created = []
    errors = []

    for entry in body.students:
        try:
            # Check if email already exists
            existing = db.table("users").select("id").eq("email", entry.email).maybe_single().execute()
            if existing.data:
                errors.append({"email": entry.email, "error": "Email already exists"})
                continue

            firebase_uid = f"mock-{entry.email}"

            if settings.AUTH_MODE == "firebase":
                try:
                    from firebase_admin import auth as fb_auth
                    fb_user = fb_auth.create_user(
                        email=entry.email, password="edunexis@2026",
                        display_name=entry.name,
                    )
                    firebase_uid = fb_user.uid
                except Exception as e:
                    errors.append({"email": entry.email, "error": str(e)})
                    continue

            user_data = {
                "tenant_id": tenant_id,
                "email": entry.email,
                "name": entry.name,
                "role": "student",
                "department_id": entry.department_id,
                "firebase_uid": firebase_uid,
                "is_active": True,
                "created_by": creator_id,
            }
            result = db.table("users").insert(user_data).execute()
            student = result.data[0]
            created.append(student)

            # Auto-add to batch if batch_code provided
            if entry.batch_code:
                batch = (
                    db.table("batches")
                    .select("id")
                    .eq("tenant_id", tenant_id)
                    .eq("code", entry.batch_code)
                    .maybe_single()
                    .execute()
                )
                if batch.data:
                    db.table("batch_students").insert({
                        "tenant_id": tenant_id,
                        "batch_id": batch.data["id"],
                        "student_id": student["id"],
                        "roll_number": entry.roll_number,
                    }).execute()

        except Exception as e:
            errors.append({"email": entry.email, "error": str(e)})

    return success_response(
        data={"created": len(created), "errors": errors, "students": created},
        message=f"Imported {len(created)} students, {len(errors)} errors",
    )


# ═══════════════════════════════════════════════════════════
# BULK IMPORT — Faculty
# ═══════════════════════════════════════════════════════════

@router.post("/bulk/faculty")
async def bulk_import_faculty(
    body: BulkImportFaculty,
    user: dict = Depends(require_role(["admin"])),
):
    """Bulk create faculty users with optional workload setup."""
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    creator_id = user.get("user_id")

    created = []
    errors = []

    for entry in body.faculty:
        try:
            existing = db.table("users").select("id").eq("email", entry.email).maybe_single().execute()
            if existing.data:
                errors.append({"email": entry.email, "error": "Email already exists"})
                continue

            firebase_uid = f"mock-{entry.email}"

            if settings.AUTH_MODE == "firebase":
                try:
                    from firebase_admin import auth as fb_auth
                    fb_user = fb_auth.create_user(
                        email=entry.email, password="edunexis@2026",
                        display_name=entry.name,
                    )
                    firebase_uid = fb_user.uid
                except Exception as e:
                    errors.append({"email": entry.email, "error": str(e)})
                    continue

            user_data = {
                "tenant_id": tenant_id,
                "email": entry.email,
                "name": entry.name,
                "role": "faculty",
                "department_id": entry.department_id,
                "firebase_uid": firebase_uid,
                "is_active": True,
                "created_by": creator_id,
            }
            result = db.table("users").insert(user_data).execute()
            faculty_user = result.data[0]
            created.append(faculty_user)

            # Create workload record
            db.table("faculty_workload").insert({
                "tenant_id": tenant_id,
                "faculty_id": faculty_user["id"],
                "max_hours_per_week": entry.max_hours_per_week,
            }).execute()

        except Exception as e:
            errors.append({"email": entry.email, "error": str(e)})

    return success_response(
        data={"created": len(created), "errors": errors, "faculty": created},
        message=f"Imported {len(created)} faculty, {len(errors)} errors",
    )


# ═══════════════════════════════════════════════════════════
# BULK IMPORT — Batches
# ═══════════════════════════════════════════════════════════

@router.post("/bulk/batches")
async def bulk_import_batches(
    body: dict,
    user: dict = Depends(require_role(["admin"])),
):
    """Bulk create batches. Each entry: {name, code, program_id, semester, max_students}"""
    db = get_supabase()
    tenant_id = get_tenant_id(user)

    batches = body.get("batches", [])
    records = [{**b, "tenant_id": tenant_id} for b in batches]
    result = db.table("batches").insert(records).execute()
    return success_response(
        data={"count": len(result.data)},
        message=f"Created {len(result.data)} batches",
    )


# ═══════════════════════════════════════════════════════════
# FACULTY WORKLOAD & ASSIGNMENTS
# ═══════════════════════════════════════════════════════════

@router.get("/faculty-assignments")
async def list_faculty_assignments(
    user: dict = Depends(require_role(["admin", "hod", "faculty"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    result = (
        db.table("faculty_assignments")
        .select("*, faculties:users!faculty_assignments_faculty_id_fkey(name, email), subjects:subjects(name, code), batches:batches(name, code)")
        .eq("tenant_id", tenant_id)
        .execute()
    )
    return success_response(data=result.data)

@router.get("/faculty-workload")
async def list_faculty_workload(
    user: dict = Depends(require_role(["admin", "hod"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)

    # Get faculty users with their workload and assignments
    faculty = (
        db.table("users")
        .select("id, name, email, department_id")
        .eq("tenant_id", tenant_id)
        .eq("role", "faculty")
        .eq("is_active", True)
        .execute()
    )

    workloads = (
        db.table("faculty_workload")
        .select("*")
        .eq("tenant_id", tenant_id)
        .execute()
    )
    workload_map = {w["faculty_id"]: w for w in workloads.data}

    assignments = (
        db.table("faculty_assignments")
        .select("*, subjects(name, code)")
        .eq("tenant_id", tenant_id)
        .execute()
    )
    assign_map: dict = {}
    for a in assignments.data:
        fid = a["faculty_id"]
        if fid not in assign_map:
            assign_map[fid] = {"subjects": [], "total_hours": 0}
        assign_map[fid]["subjects"].append(a)
        assign_map[fid]["total_hours"] += a.get("hours_per_week", 4)

    result = []
    for f in faculty.data:
        wl = workload_map.get(f["id"], {})
        asgn = assign_map.get(f["id"], {"subjects": [], "total_hours": 0})
        result.append({
            **f,
            "max_hours_per_week": wl.get("max_hours_per_week", 20),
            "current_hours_per_week": asgn["total_hours"],
            "assigned_subjects": asgn["subjects"],
            "utilization": round(asgn["total_hours"] / wl.get("max_hours_per_week", 20) * 100) if wl.get("max_hours_per_week") else 0,
        })

    return success_response(data=result)


@router.patch("/faculty-workload/{faculty_id}")
async def update_faculty_workload(
    faculty_id: str,
    body: FacultyWorkloadUpdate,
    user: dict = Depends(require_role(["admin"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    result = (
        db.table("faculty_workload")
        .upsert({
            "tenant_id": tenant_id,
            "faculty_id": faculty_id,
            **body.model_dump(),
        }, on_conflict="tenant_id,faculty_id")
        .execute()
    )
    return success_response(data=result.data, message="Workload updated")


@router.post("/faculty-assignments")
async def create_faculty_assignment(
    body: FacultyAssignmentExtended,
    user: dict = Depends(require_role(["admin"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    data = {**body.model_dump(), "tenant_id": tenant_id}
    result = db.table("faculty_assignments").insert(data).execute()

    # Update current workload hours
    try:
        total = (
            db.table("faculty_assignments")
            .select("hours_per_week")
            .eq("tenant_id", tenant_id)
            .eq("faculty_id", body.faculty_id)
            .execute()
        )
        total_hours = sum(a.get("hours_per_week", 4) for a in total.data)
        db.table("faculty_workload").upsert({
            "tenant_id": tenant_id,
            "faculty_id": body.faculty_id,
            "current_hours_per_week": total_hours,
        }, on_conflict="tenant_id,faculty_id").execute()
    except Exception:
        pass

    return success_response(data=result.data, message="Faculty assigned to subject")


# ═══════════════════════════════════════════════════════════
# TIMETABLE — CRUD + Generation
# ═══════════════════════════════════════════════════════════

@router.get("/period-templates")
async def get_period_templates(
    user: dict = Depends(require_role(["admin", "hod", "faculty"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    result = db.table("period_templates").select("*").eq("tenant_id", tenant_id).order("period_number").execute()
    # If no custom templates, return defaults
    if not result.data:
        result = db.table("period_templates").select("*").order("period_number").execute()
    return success_response(data=result.data)


@router.post("/period-templates")
async def set_period_templates(
    body: dict,
    user: dict = Depends(require_role(["admin"])),
):
    """Set period timings for the institution. Body: {periods: [{period_number, start_time, end_time, label, is_break}]}"""
    db = get_supabase()
    tenant_id = get_tenant_id(user)

    periods = body.get("periods", [])
    # Clear existing
    db.table("period_templates").delete().eq("tenant_id", tenant_id).execute()

    records = [{**p, "tenant_id": tenant_id} for p in periods]
    result = db.table("period_templates").insert(records).execute()
    return success_response(data=result.data, message="Period templates saved")


@router.post("/timetable/slots")
async def create_timetable_slot(
    body: TimetableSlotCreate,
    user: dict = Depends(require_role(["admin"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    data = {**body.model_dump(), "tenant_id": tenant_id}
    try:
        result = db.table("timetable_slots").insert(data).execute()
    except Exception as e:
        error_msg = str(e)
        if "unique" in error_msg.lower() or "duplicate" in error_msg.lower():
            raise HTTPException(status_code=409, detail="Conflict: This slot is already occupied (batch/faculty/room clash)")
        raise
    return success_response(data=result.data, message="Timetable slot created")


@router.get("/timetable/batch/{batch_id}")
async def get_batch_timetable(
    batch_id: str,
    user: dict = Depends(require_role(["admin", "hod", "faculty", "student"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    result = (
        db.table("timetable_slots")
        .select("*, subjects(name, code), users!timetable_slots_faculty_id_fkey(name), classrooms(name, code)")
        .eq("tenant_id", tenant_id)
        .eq("batch_id", batch_id)
        .eq("is_active", True)
        .order("day_of_week")
        .order("period_number")
        .execute()
    )

    # Organize into a grid: day_of_week → period_number → slot
    grid: dict = {}
    for slot in result.data:
        day = slot["day_of_week"]
        if day not in grid:
            grid[day] = {}
        grid[day][slot["period_number"]] = slot

    return success_response(data={"slots": result.data, "grid": grid})


@router.get("/timetable/faculty/{faculty_id}")
async def get_faculty_timetable(
    faculty_id: str,
    user: dict = Depends(require_role(["admin", "hod", "faculty"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    result = (
        db.table("timetable_slots")
        .select("*, subjects(name, code), batches(name, code), classrooms(name, code)")
        .eq("tenant_id", tenant_id)
        .eq("faculty_id", faculty_id)
        .eq("is_active", True)
        .order("day_of_week")
        .order("period_number")
        .execute()
    )

    grid: dict = {}
    for slot in result.data:
        day = slot["day_of_week"]
        if day not in grid:
            grid[day] = {}
        grid[day][slot["period_number"]] = slot

    return success_response(data={"slots": result.data, "grid": grid})


@router.delete("/timetable/slots/{slot_id}")
async def delete_timetable_slot(
    slot_id: str,
    user: dict = Depends(require_role(["admin"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    db.table("timetable_slots").delete().eq("id", slot_id).eq("tenant_id", tenant_id).execute()
    return success_response(message="Slot deleted")


@router.post("/timetable/generate")
async def generate_timetable(
    body: TimetableGenerate,
    user: dict = Depends(require_role(["admin"])),
):
    """
    Auto-generate a timetable for a batch based on:
    - Faculty assignments for subjects in the batch's semester
    - Available classrooms
    - Period templates
    - Faculty workload limits

    Uses a greedy allocation algorithm.
    """
    db = get_supabase()
    tenant_id = get_tenant_id(user)
    batch_id = body.batch_id

    # Get batch info
    batch = db.table("batches").select("*, programs(code)").eq("id", batch_id).eq("tenant_id", tenant_id).maybe_single().execute()
    if not batch.data:
        raise HTTPException(status_code=404, detail="Batch not found")

    semester = batch.data.get("semester", 1)

    # Clear existing timetable if regenerating
    if body.force_regenerate:
        db.table("timetable_slots").delete().eq("tenant_id", tenant_id).eq("batch_id", batch_id).execute()

    # Get subjects for this semester
    subjects = (
        db.table("subjects")
        .select("id, name, code, max_marks")
        .eq("tenant_id", tenant_id)
        .eq("semester", semester)
        .execute()
    )

    # Get faculty assignments for these subjects
    subject_ids = [s["id"] for s in subjects.data]
    if not subject_ids:
        raise HTTPException(status_code=400, detail="No subjects found for this batch's semester")

    assignments = (
        db.table("faculty_assignments")
        .select("faculty_id, subject_id, hours_per_week")
        .eq("tenant_id", tenant_id)
        .in_("subject_id", subject_ids)
        .execute()
    )

    # Get period templates
    templates = (
        db.table("period_templates")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("is_break", False)
        .order("period_number")
        .execute()
    )
    if not templates.data:
        # Use default periods
        templates = db.table("period_templates").select("*").eq("is_break", False).order("period_number").execute()

    periods = templates.data
    if not periods:
        raise HTTPException(status_code=400, detail="No period templates set up")

    # Get available classrooms
    rooms = (
        db.table("classrooms")
        .select("id, name, code, capacity")
        .eq("tenant_id", tenant_id)
        .eq("is_available", True)
        .order("capacity", desc=True)
        .execute()
    )

    # Track occupied slots
    existing = (
        db.table("timetable_slots")
        .select("faculty_id, day_of_week, period_number, classroom_id, batch_id")
        .eq("tenant_id", tenant_id)
        .execute()
    )

    faculty_occupied: dict = {}
    room_occupied: dict = {}
    batch_occupied: dict = {}
    for s in existing.data:
        key_f = f"{s['faculty_id']}-{s['day_of_week']}-{s['period_number']}"
        key_r = f"{s.get('classroom_id','')}-{s['day_of_week']}-{s['period_number']}"
        key_b = f"{s['batch_id']}-{s['day_of_week']}-{s['period_number']}"
        faculty_occupied[key_f] = True
        if s.get("classroom_id"):
            room_occupied[key_r] = True
        batch_occupied[key_b] = True

    # Greedy allocation
    created_slots = []
    days = [1, 2, 3, 4, 5, 6]  # Mon-Sat

    for asgn in assignments.data:
        hrs_needed = asgn.get("hours_per_week", 4)
        allocated = 0

        for day in days:
            if allocated >= hrs_needed:
                break
            for period in periods:
                if allocated >= hrs_needed:
                    break

                pnum = period["period_number"]
                fid = asgn["faculty_id"]

                # Check conflicts
                key_f = f"{fid}-{day}-{pnum}"
                key_b = f"{batch_id}-{day}-{pnum}"

                if key_f in faculty_occupied or key_b in batch_occupied:
                    continue

                # Find an available room
                room_id = None
                for room in rooms.data:
                    key_r = f"{room['id']}-{day}-{pnum}"
                    if key_r not in room_occupied:
                        room_id = room["id"]
                        break

                slot_data = {
                    "tenant_id": tenant_id,
                    "batch_id": batch_id,
                    "subject_id": asgn["subject_id"],
                    "faculty_id": fid,
                    "classroom_id": room_id,
                    "day_of_week": day,
                    "period_number": pnum,
                    "start_time": period["start_time"],
                    "end_time": period["end_time"],
                    "slot_type": "lecture",
                }

                try:
                    result = db.table("timetable_slots").insert(slot_data).execute()
                    created_slots.append(result.data[0])

                    # Mark as occupied
                    faculty_occupied[key_f] = True
                    batch_occupied[key_b] = True
                    if room_id:
                        room_occupied[f"{room_id}-{day}-{pnum}"] = True

                    allocated += 1
                except Exception:
                    continue

    return success_response(
        data={
            "allocated_slots": len(created_slots),
            "total_assignments": len(assignments.data),
            "slots": created_slots,
        },
        message=f"Generated timetable: {len(created_slots)} slots allocated",
    )
