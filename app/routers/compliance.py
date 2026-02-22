"""
Compliance router — Semester summary, CSV export, PDF export.
All queries tenant-isolated.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from app.core.security import require_role
from app.core.middleware import get_tenant_id
from app.core.database import get_supabase
from app.utils.response import success_response
import csv
import io

router = APIRouter(prefix="/api/compliance", tags=["Compliance"])


@router.get("/semester-summary")
async def semester_summary(
    user: dict = Depends(require_role(["admin", "super_admin"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)

    # Count students
    students = db.table("users").select("id", count="exact").eq("tenant_id", tenant_id).eq("role", "student").eq("is_active", True).execute()
    student_count = students.count or 0

    # Count faculty
    faculty = db.table("users").select("id", count="exact").eq("tenant_id", tenant_id).eq("role", "faculty").eq("is_active", True).execute()
    faculty_count = faculty.count or 0

    # Marks summary
    marks = (
        db.table("internal_marks")
        .select("subject_id, marks, max_marks, subjects(name, code)")
        .eq("tenant_id", tenant_id)
        .eq("status", "locked")
        .execute()
    )

    subject_perf = {}
    total_marks_sum = 0
    total_max_sum = 0
    for m in marks.data:
        sid = m["subject_id"]
        subj = m.get("subjects", {})
        if sid not in subject_perf:
            subject_perf[sid] = {
                "subject_id": sid,
                "subject_name": subj.get("name", ""),
                "subject_code": subj.get("code", ""),
                "total_marks": 0,
                "total_max": 0,
                "student_count": 0,
            }
        subject_perf[sid]["total_marks"] += float(m["marks"] or 0)
        subject_perf[sid]["total_max"] += int(m["max_marks"] or 100)
        subject_perf[sid]["student_count"] += 1
        total_marks_sum += float(m["marks"] or 0)
        total_max_sum += int(m["max_marks"] or 100)

    subject_performance = []
    for sp in subject_perf.values():
        avg = sp["total_marks"] / sp["student_count"] if sp["student_count"] > 0 else 0
        subject_performance.append({
            **sp,
            "average_marks": round(avg, 2),
            "max_marks": sp["total_max"] // sp["student_count"] if sp["student_count"] > 0 else 100,
        })

    pass_pct = round((total_marks_sum / total_max_sum * 100) if total_max_sum > 0 else 0, 2)

    # Attendance average
    attendance = db.table("attendance").select("status").eq("tenant_id", tenant_id).execute()
    total_att = len(attendance.data) if attendance.data else 0
    present_att = sum(1 for a in attendance.data if a["status"] in ("present", "od")) if attendance.data else 0
    att_avg = round((present_att / total_att * 100) if total_att > 0 else 0, 2)

    ratio = round(student_count / faculty_count, 1) if faculty_count > 0 else 0

    return success_response(data={
        "student_count": student_count,
        "faculty_count": faculty_count,
        "student_faculty_ratio": ratio,
        "pass_percentage": pass_pct,
        "attendance_average": att_avg,
        "subject_performance": subject_performance,
    })


@router.get("/export/csv")
async def export_csv(
    user: dict = Depends(require_role(["admin"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)

    marks = (
        db.table("internal_marks")
        .select("*, users!internal_marks_student_id_fkey(name, email), subjects(name, code)")
        .eq("tenant_id", tenant_id)
        .eq("status", "locked")
        .execute()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Student Name", "Email", "Subject", "Subject Code", "Marks", "Max Marks", "Percentage", "Status"])

    for m in marks.data:
        student = m.get("users", {})
        subject = m.get("subjects", {})
        pct = round(float(m["marks"]) / int(m["max_marks"]) * 100, 2) if m["marks"] and m["max_marks"] else 0
        writer.writerow([
            student.get("name", ""),
            student.get("email", ""),
            subject.get("name", ""),
            subject.get("code", ""),
            m["marks"],
            m["max_marks"],
            f"{pct}%",
            m["status"],
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=edunexis_compliance_report.csv"},
    )


@router.get("/export/pdf")
async def export_pdf(
    user: dict = Depends(require_role(["admin"])),
):
    db = get_supabase()
    tenant_id = get_tenant_id(user)

    marks = (
        db.table("internal_marks")
        .select("*, users!internal_marks_student_id_fkey(name, email), subjects(name, code)")
        .eq("tenant_id", tenant_id)
        .eq("status", "locked")
        .execute()
    )

    try:
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = []

        elements.append(Paragraph("EduNexis — Compliance Report", styles["Title"]))
        elements.append(Spacer(1, 20))

        table_data = [["Student", "Subject", "Code", "Marks", "Max", "%", "Status"]]
        for m in marks.data:
            student = m.get("users", {})
            subject = m.get("subjects", {})
            pct = round(float(m["marks"]) / int(m["max_marks"]) * 100, 1) if m["marks"] and m["max_marks"] else 0
            table_data.append([
                student.get("name", ""),
                subject.get("name", ""),
                subject.get("code", ""),
                str(m["marks"]),
                str(m["max_marks"]),
                f"{pct}%",
                m["status"],
            ])

        table = Table(table_data)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#142B34")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ALIGN", (3, 1), (5, -1), "CENTER"),
        ]))
        elements.append(table)

        doc.build(elements)
        buffer.seek(0)

        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=edunexis_compliance_report.pdf"},
        )
    except ImportError:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="ReportLab not installed. Run: pip install reportlab")
