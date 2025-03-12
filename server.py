from typing import Any
import httpx
import asyncio
from mcp.server.fastmcp import FastMCP
import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

mcp = FastMCP("hemis_student")

HEMIS_API_BASE = os.getenv("HEMIS_API_BASE")
STUDENT_LOGIN = os.getenv("HEMIS_LOGIN")
STUDENT_PASSWORD = os.getenv("HEMIS_PASSWORD")
TOKEN_CACHE_FILE = os.path.join(os.path.dirname(__file__), 'token_cache.json')

_cached_token = None
_token_expiry = None

# ----------------------------- helpers -----------------------------------------

async def make_get_request(url: str, token: str = None) -> dict[str, Any] | None:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

async def make_post_request(url: str, data: dict[str, Any]) -> dict[str, Any] | None:
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=data, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None
        
async def save_token(token: str) -> None:
    global _cached_token, _token_expiry
    
    expiry = datetime.now() + timedelta(days=7)
    _cached_token = token
    _token_expiry = expiry.isoformat()
    
    try:
        with open(TOKEN_CACHE_FILE, 'w') as f:
            json.dump({
                'token': token,
                'expiry': _token_expiry
            }, f)
    except Exception:
        pass

async def get_cached_token() -> str | None:
    global _cached_token, _token_expiry
    
    if _cached_token and _token_expiry:
        expiry = datetime.fromisoformat(_token_expiry)
        if datetime.now() < expiry:
            return _cached_token
    
    try:
        if os.path.exists(TOKEN_CACHE_FILE):
            with open(TOKEN_CACHE_FILE, 'r') as f:
                data = json.load(f)
                token = data.get('token')
                expiry_str = data.get('expiry')
                
                if token and expiry_str:
                    expiry = datetime.fromisoformat(expiry_str)
                    if datetime.now() < expiry:
                        _cached_token = token
                        _token_expiry = expiry_str
                        return token
    except Exception:
        pass
    
    return None
        
async def login_to_hemis() -> str | None:
    cached_token = await get_cached_token()
    if cached_token:
        return cached_token
    
    endpoint = "auth/login"
    url = f"{HEMIS_API_BASE}{endpoint}"
    
    if not STUDENT_LOGIN or not STUDENT_PASSWORD:
        return None
    
    login_data = {
        "login": STUDENT_LOGIN,
        "password": STUDENT_PASSWORD
    }
    
    response = await make_post_request(url, login_data)
    
    if not response or not response.get("success"):
        return None
    
    token = response["data"]["token"]
    
    await save_token(token)
    
    return token

# ----------------------------- student -----------------------------------------

@mcp.tool()
async def get_student_profile(language: str = "en-US") -> str:
    """Get your personal and academic information from HEMIS.
    
    Args:
        language: Language for the response (e.g. en-US, uz-UZ)
    """
    token = await login_to_hemis()
    
    if not token:
        return "Unable to authenticate with HEMIS. Please check your credentials."
    
    endpoint = "account/me"
    url = f"{HEMIS_API_BASE}{endpoint}?l={language}"
    
    data = await make_get_request(url, token)
    
    if not data or not data.get("success"):
        return "Unable to fetch student profile information."
    
    profile = data["data"]
    result = []
    
    result.append("\n## Personal Information")
    result.append(f"- Full Name: {profile['first_name']} {profile['second_name']} {profile['third_name']}")
    result.append(f"- Student ID: {profile['student_id_number']}")
    
    if profile.get('birth_date'):
        from datetime import datetime
        birth_date = datetime.fromtimestamp(profile['birth_date']).strftime('%Y-%m-%d')
        result.append(f"- Birth Date: {birth_date}")
    
    result.append(f"- Gender: {profile['gender']['name']}")
    result.append(f"- Passport Number: {profile['passport_number']}")
    result.append(f"- Passport PIN: {profile['passport_pin']}")
    result.append(f"- Phone: {profile['phone']}")
    
    if profile.get('email') and profile['email']:
        result.append(f"- Email: {profile['email']}")
    
    result.append("\n## Address Information")
    result.append(f"- Country: {profile['country']['name']}")
    result.append(f"- Province: {profile['province']['name']}")
    result.append(f"- District: {profile['district']['name']}")
    result.append(f"- Address: {profile['address']}")
    result.append(f"- Accommodation: {profile['accommodation']['name']}")
    
    result.append("\n## Academic Information")
    result.append(f"- University: {profile['university']}")
    result.append(f"- Faculty: {profile['faculty']['name']} ({profile['faculty']['code']})")
    result.append(f"- Specialty: {profile['specialty']['name']} ({profile['specialty']['code']})")
    result.append(f"- Group: {profile['group']['name']}")
    result.append(f"- Education Form: {profile['educationForm']['name']}")
    result.append(f"- Education Type: {profile['educationType']['name']}")
    result.append(f"- Education Language: {profile['educationLang']['name']}")
    result.append(f"- Payment Form: {profile['paymentForm']['name']}")
    result.append(f"- Course Level: {profile['level']['name']}")
    result.append(f"- Current Semester: {profile['semester']['name']}")
    result.append(f"- Academic Year: {profile['semester']['education_year']['name']}")
    result.append(f"- Student Status: {profile['studentStatus']['name']}")
    
    return "\n".join(result)

@mcp.tool()
async def get_student_gpa_list(language: str = "en-US") -> str:
    """Get your GPA information across academic years from HEMIS.
    
    Args:
        language: Language for the response (e.g. en-US, uz-UZ)
    """
    token = await login_to_hemis()
    
    if not token:
        return "Unable to authenticate with HEMIS. Please check your credentials."
    
    endpoint = "education/gpa-list"
    url = f"{HEMIS_API_BASE}{endpoint}?l={language}"
    
    data = await make_get_request(url, token)
    
    if not data or not data.get("success"):
        return "Unable to fetch GPA information."
    
    gpa_list = data["data"]
    result = ["# GPA History"]
    
    if not gpa_list:
        result.append("\nNo GPA records found.")
        return "\n".join(result)
    
    gpa_list.sort(key=lambda x: x["educationYear"]["code"], reverse=True)
    
    for gpa_record in gpa_list:
        year = gpa_record["educationYear"]["name"]
        level = gpa_record["level"]["name"]
        gpa = gpa_record["gpa"]
        credit_sum = gpa_record["credit_sum"]
        subjects = gpa_record["subjects"]
        debt_subjects = gpa_record["debt_subjects"]
        
        result.append(f"\n## {year} ({level})")
        result.append(f"- GPA: {gpa}")
        result.append(f"- Total Credits: {credit_sum}")
        result.append(f"- Subjects: {subjects}")
        
        if debt_subjects > 0:
            result.append(f"- Debt Subjects: {debt_subjects}")
        
        if gpa_record.get("can_transfer"):
            result.append("- Eligible for transfer to next course: Yes")
        else:
            result.append("- Eligible for transfer to next course: No")
        
        method = gpa_record.get("method", "")
        if method == "one_year":
            result.append("- Calculation method: One year")
        elif method == "all_year":
            result.append("- Calculation method: All years")
    
    return "\n".join(result)

@mcp.tool()
async def get_student_semesters(language: str = "en-US") -> str:
    """Get your semester information across academic years from HEMIS.
    
    Args:
        language: Language for the response (e.g. en-US, uz-UZ)
    """
    token = await login_to_hemis()
    
    if not token:
        return "Unable to authenticate with HEMIS. Please check your credentials."
    
    endpoint = "education/semesters"
    url = f"{HEMIS_API_BASE}{endpoint}?l={language}"
    
    data = await make_get_request(url, token)
    
    if not data or not data.get("success"):
        return "Unable to fetch semester information."
    
    semesters = data["data"]
    result = ["# Academic Semester History"]
    
    if not semesters:
        result.append("\nNo semester records found.")
        return "\n".join(result)
    
    semesters.sort(key=lambda x: (x["education_year"]["code"], x["code"]))
    
    current_year = None
    for semester in semesters:
        year = semester["education_year"]["name"]
        
        if year != current_year:
            result.append(f"\n## Academic Year: {year}")
            if semester["education_year"].get("current"):
                result.append("*Current academic year*")
            current_year = year
        
        result.append(f"\n### Semester code: {semester["code"]}")
        
        if semester["current"]:
            result.append("**Current semester**")
        
        if semester.get("weeks") and len(semester["weeks"]) > 0:
            weeks = semester["weeks"]
            from datetime import datetime
            
            first_week = min(weeks, key=lambda w: w["start_date"])
            last_week = max(weeks, key=lambda w: w["end_date"])
            
            start_date = datetime.fromtimestamp(first_week["start_date"]).strftime('%Y-%m-%d')
            end_date = datetime.fromtimestamp(last_week["end_date"]).strftime('%Y-%m-%d')
            
            result.append(f"- Start Date: {start_date}")
            result.append(f"- End Date: {end_date}")
            result.append(f"- Number of Weeks: {len(weeks)}")
            
            current_weeks = [w for w in weeks if w.get("current")]
            if current_weeks:
                current_week = current_weeks[0]
                result.append(f"- Current Week: {current_week['start_date_f']} to {current_week['end_date_f']}")
    
    return "\n".join(result)

@mcp.tool()
async def get_student_subjects(semester: str | int, language: str = "en-US") -> str:
    """Get your subjects and grades for a specific semester from HEMIS.
    
    Args:
        semester: Semester code to get subjects for (e.g. "14" for 4th semester")
        language: Language for the response (e.g. en-US, uz-UZ)
    """
    token = await login_to_hemis()
    
    if not token:
        return "Unable to authenticate with HEMIS. Please check your credentials."
    
    endpoint = "education/subject-list"
    url = f"{HEMIS_API_BASE}{endpoint}?l={language}&semester={semester}"
    
    data = await make_get_request(url, token)
    
    if not data or not data.get("success"):
        return "Unable to fetch subject information for the specified semester."
    
    subjects = data["data"]
    result = [f"# Subject List for Semester {semester}"]
    
    if not subjects:
        result.append("\nNo subjects found for this semester.")
        return "\n".join(result)
    
    total_credits = sum(subject["curriculumSubject"]["credit"] for subject in subjects)
    result.append(f"\n**Total Credits:** {total_credits}\n")
    
    subjects.sort(key=lambda x: x["curriculumSubject"]["subject"]["name"])
    
    for subject in subjects:
        curriculum = subject["curriculumSubject"]
        subject_data = curriculum["subject"]
        
        result.append(f"## {subject_data['name']} ({subject_data['code']})")
        result.append(f"- Subject Type: {curriculum['subjectType']['name']}")
        result.append(f"- Credit Hours: {curriculum['credit']}")
        result.append(f"- Total Academic Load: {curriculum['total_acload']} hours")
        
        if subject.get("overallScore"):
            overall = subject["overallScore"]
            result.append(f"- **Grade: {overall['grade']} / {overall['max_ball']} ({overall['percent']}%)**")
            result.append(f"- Exam Type: {overall['examType']['name']}")
        
        if subject.get("gradesByExam") and len(subject["gradesByExam"]) > 0:
            result.append("\n### Exam Grades")
            for exam in subject["gradesByExam"]:
                result.append(f"- {exam['examType']['name']}: {exam['grade']} / {exam['max_ball']} ({exam['percent']}%)")
        
        result.append("")
    
    return "\n".join(result)

@mcp.tool()
async def get_student_subjects_list(semester: str | int, language: str = "en-US") -> str:
    """Get your subjects list for a specific semester from HEMIS (without grades).
    
    Args:
        semester: Semester code to get subjects for (e.g. "14" for 4th semester")
        language: Language for the response (e.g. en-US, uz-UZ)
    """
    token = await login_to_hemis()
    
    if not token:
        return "Unable to authenticate with HEMIS. Please check your credentials."
    
    endpoint = "education/subjects"
    url = f"{HEMIS_API_BASE}{endpoint}?l={language}&semester={semester}"
    
    data = await make_get_request(url, token)
    
    if not data or not data.get("success"):
        return "Unable to fetch subjects list for the specified semester."
    
    subjects = data["data"]
    result = [f"# Subject List for Semester {semester}"]
    
    if not subjects:
        result.append("\nNo subjects found for this semester.")
        return "\n".join(result)
    
    total_credits = sum(subject.get("credit", 0) for subject in subjects)
    total_hours = sum(subject.get("total_acload", 0) for subject in subjects)
    result.append(f"\n**Total Credits:** {total_credits}")
    result.append(f"**Total Academic Hours:** {total_hours}\n")
    
    # Sort subjects alphabetically by name
    subjects.sort(key=lambda x: x["subject"]["name"])
    
    for subject in subjects:
        subject_data = subject["subject"]
        subject_type = subject["subjectType"]
        
        result.append(f"## {subject_data['name']} ({subject_data['code']})")
        result.append(f"- Subject ID: {subject_data['id']}")
        result.append(f"- Subject Type: {subject_type['name']} ({subject_type['code']})")
        result.append(f"- Credit Hours: {subject['credit']}")
        result.append(f"- Total Academic Load: {subject['total_acload']} hours")
        result.append("")
    
    return "\n".join(result)

@mcp.tool()
async def get_student_attendance(subject: str | int, semester: str | int, language: str = "en-US") -> str:
    """Get your attendance information for a specific subject in a semester from HEMIS.
    
    Args:
        subject: Subject ID to get attendance for
        semester: Semester code to get subjects for (e.g. "14" for 4th semester")
        language: Language for the response (e.g. en-US, uz-UZ)
    """
    token = await login_to_hemis()
    
    if not token:
        return "Unable to authenticate with HEMIS. Please check your credentials."
    
    endpoint = "education/attendance"
    url = f"{HEMIS_API_BASE}{endpoint}?l={language}&subject={subject}&semester={semester}"
    
    data = await make_get_request(url, token)
    
    if not data or not data.get("success"):
        return "Unable to fetch attendance information for the specified subject and semester."
    
    attendance_records = data["data"]
    
    if not attendance_records:
        return "No attendance records found for this subject in the specified semester."
    
    first_record = attendance_records[0]
    subject_info = first_record.get("subject", {})
    subject_name = subject_info.get("name", "Unknown Subject")
    subject_code = subject_info.get("code", "")
    
    result = [f"# Attendance for {subject_name} ({subject_code})"]
    
    total_lessons = len(attendance_records)
    absent_count = sum(1 for record in attendance_records if record.get("absent_on") or record.get("absent_off"))
    explicable_absences = sum(1 for record in attendance_records if 
                             (record.get("absent_on") or record.get("absent_off")) and record.get("explicable"))
    
    result.append(f"\n**Total Lessons:** {total_lessons}")
    result.append(f"**Absences:** {absent_count}")
    result.append(f"**Excused Absences:** {explicable_absences}")
    result.append(f"**Attendance Rate:** {((total_lessons - absent_count) / total_lessons * 100):.1f}%")
    
    attendance_records.sort(key=lambda x: x.get("lesson_date", 0))
    
    result.append("\n## Attendance Records")
    
    for record in attendance_records:
        from datetime import datetime
        
        if record.get("lesson_date"):
            date = datetime.fromtimestamp(record["lesson_date"]).strftime('%Y-%m-%d')
        else:
            date = "Unknown Date"
        
        training_type = record.get("trainingType", {}).get("name", "Unknown Type")
        
        lesson_pair = record.get("lessonPair", {})
        start_time = lesson_pair.get("start_time", "")
        end_time = lesson_pair.get("end_time", "")
        time_info = f"{start_time}-{end_time}" if start_time and end_time else "Unknown time"
        
        employee = record.get("employee", {}).get("name", "Unknown Instructor")
        
        status = "Present"
        if record.get("absent_on") or record.get("absent_off"):
            if record.get("explicable"):
                status = "Excused Absence"
            else:
                status = "Unexcused Absence"
        
        result.append(f"- **{date}** ({training_type}, {time_info})")
        result.append(f"  - Instructor: {employee}")
        result.append(f"  - Status: {status}")
    
    return "\n".join(result)

@mcp.tool()
async def get_student_exams(semester: str | int, language: str = "en-US") -> str:
    """Get your exam schedule for a specific semester from HEMIS.
    
    Args:
        semester: Semester code to get subjects for (e.g. "14" for 4th semester")
        language: Language for the response (e.g. en-US, uz-UZ)
    """
    token = await login_to_hemis()
    
    if not token:
        return "Unable to authenticate with HEMIS. Please check your credentials."
    
    endpoint = "education/exam-table"
    url = f"{HEMIS_API_BASE}{endpoint}?l={language}&semester={semester}"
    
    data = await make_get_request(url, token)
    
    if not data or not data.get("success"):
        return "Unable to fetch exam schedule for the specified semester."
    
    exam_records = data["data"]
    result = [f"# Exam Schedule for Semester {semester}"]
    
    if not exam_records:
        result.append("\nNo exams scheduled for this semester.")
        return "\n".join(result)
    
    exam_records.sort(key=lambda x: x.get("examDate", 0))
    
    if exam_records:
        first_exam = exam_records[0]
        education_year = first_exam.get("educationYear", {}).get("name", "Unknown Academic Year")
        group = first_exam.get("group", {}).get("name", "Unknown Group")
        result.append(f"\nAcademic Year: **{education_year}**")
        result.append(f"Group: **{group}**")
    
    result.append("\n## Scheduled Exams")
    
    for exam in exam_records:
        from datetime import datetime
        
        subject_info = exam.get("subject", {})
        subject_name = subject_info.get("name", "Unknown Subject")
        subject_code = subject_info.get("code", "")
        
        exam_date_ts = exam.get("examDate", 0)
        if exam_date_ts:
            exam_date = datetime.fromtimestamp(exam_date_ts).strftime('%Y-%m-%d')
        else:
            exam_date = "Date not specified"
        
        lesson_pair = exam.get("lessonPair", {})
        start_time = lesson_pair.get("start_time", "")
        end_time = lesson_pair.get("end_time", "")
        time_info = f"{start_time}-{end_time}" if start_time and end_time else "Time not specified"
        
        exam_type = exam.get("examType", {}).get("name", "Unknown Type")
        final_exam_type = exam.get("finalExamType", {}).get("name", "")
        
        instructor = exam.get("employee", {}).get("name", "Not specified")
        
        auditorium = exam.get("auditorium", {})
        room = auditorium.get("name", "Not specified")
        building = auditorium.get("building", {}).get("name", "")
        location = f"{room}, {building}" if building else room
        
        result.append(f"\n### {subject_name} ({subject_code})")
        result.append(f"- **Date:** {exam_date}")
        result.append(f"- **Time:** {time_info}")
        result.append(f"- **Exam Type:** {exam_type}")
        if final_exam_type:
            result.append(f"- **Final Exam Type:** {final_exam_type}")
        result.append(f"- **Instructor:** {instructor}")
        result.append(f"- **Location:** {location}")
        
        department = exam.get("department", {}).get("name", "")
        faculty = exam.get("faculty", {}).get("name", "")
        if department:
            result.append(f"- **Department:** {department}")
        if faculty:
            result.append(f"- **Faculty:** {faculty}")
    
    return "\n".join(result)

@mcp.tool()
async def get_student_performance(subject: str | int, semester: str | int, language: str = "en-US") -> str:
    """Get your performance and task information for a specific subject in a semester from HEMIS.
    
    Args:
        subject: Subject ID to get performance data for
        semester: Semester code to get subjects for (e.g. "14" for 4th semester")
        language: Language for the response (e.g. en-US, uz-UZ)
    """
    token = await login_to_hemis()
    
    if not token:
        return "Unable to authenticate with HEMIS. Please check your credentials."
    
    endpoint = "education/performance"
    url = f"{HEMIS_API_BASE}{endpoint}?l={language}&subject={subject}&semester={semester}"
    
    data = await make_get_request(url, token)
    
    if not data or not data.get("success"):
        return "Unable to fetch performance information for the specified subject and semester."
    
    performance = data["data"]
    
    if not performance:
        return "No performance data found for this subject in the specified semester."
    
    subject_info = performance.get("subject", {})
    subject_name = subject_info.get("name", "Unknown Subject")
    subject_code = subject_info.get("code", "")
    
    result = [f"# Performance for {subject_name} ({subject_code})"]
    
    subject_type = performance.get("subjectType", {}).get("name", "Unknown Type")
    credit = performance.get("credit", 0)
    total_acload = performance.get("total_acload", 0)
    
    result.append("\n## Subject Information")
    result.append(f"- Subject Type: {subject_type}")
    result.append(f"- Credit Hours: {credit}")
    if total_acload:
        result.append(f"- Total Academic Load: {total_acload} hours")
    
    tasks_count = performance.get("tasks_count", 0)
    submits_count = performance.get("submits_count", 0)
    marked_count = performance.get("marked_count", 0)
    resources_count = performance.get("resources_count", 0)
    absent_count = performance.get("absent_count", 0)
    
    result.append("\n## Task Statistics")
    result.append(f"- Total Tasks: {tasks_count}")
    result.append(f"- Submitted Tasks: {submits_count}")
    result.append(f"- Marked Tasks: {marked_count}")
    result.append(f"- Available Resources: {resources_count}")
    result.append(f"- Absences: {absent_count}")
    
    tasks = performance.get("tasks", [])
    
    if tasks:
        result.append("\n## Task Details")
        
        tasks.sort(key=lambda x: x.get("deadline", 0) or 0)
        
        for task in tasks:
            task_name = task.get("name", "Unnamed Task")
            result.append(f"\n### {task_name}")
            
            training_type = task.get("trainingType", {}).get("name", "")
            if training_type:
                result.append(f"- Training Type: {training_type}")
            
            task_type = task.get("taskType", {}).get("name", "")
            if task_type:
                result.append(f"- Task Type: {task_type}")
                
            max_ball = task.get("max_ball")
            if max_ball is not None:
                result.append(f"- Maximum Score: {max_ball}")
            
            deadline = task.get("deadline")
            if deadline:
                from datetime import datetime
                deadline_date = datetime.fromtimestamp(deadline).strftime('%Y-%m-%d %H:%M')
                result.append(f"- Deadline: {deadline_date}")
                
            attempt_limit = task.get("attempt_limit")
            if attempt_limit:
                result.append(f"- Attempt Limit: {attempt_limit}")
                
            task_status = task.get("taskStatus", {}).get("name", "")
            if task_status:
                result.append(f"- Status: {task_status}")
                
            employee = task.get("employee", {}).get("name", "")
            if employee:
                result.append(f"- Instructor: {employee}")
                
            comment = task.get("comment")
            if comment:
                result.append(f"- Comment: {comment}")
                
            files = task.get("files", [])
            if files:
                result.append("\n#### Attached Files:")
                for file in files:
                    file_name = file.get("name", "Unnamed file")
                    file_size = file.get("size", 0)
                    file_url = file.get("url", "")
                    
                    size_display = f"{file_size} bytes"
                    if file_size > 1024 * 1024:
                        size_display = f"{file_size / (1024 * 1024):.2f} MB"
                    elif file_size > 1024:
                        size_display = f"{file_size / 1024:.2f} KB"
                        
                    if file_url:
                        result.append(f"- [{file_name}]({file_url}) ({size_display})")
                    else:
                        result.append(f"- {file_name} ({size_display})")
    else:
        result.append("\nNo tasks assigned for this subject.")
    
    return "\n".join(result)

@mcp.tool()
async def get_student_contract(language: str = "en-US") -> str:
    """Get your contract information for the current academic year from HEMIS.
    
    Args:
        language: Language for the response (e.g. en-US, uz-UZ)
    """
    token = await login_to_hemis()
    
    if not token:
        return "Unable to authenticate with HEMIS. Please check your credentials."
    
    endpoint = "student/contract"
    url = f"{HEMIS_API_BASE}{endpoint}?l={language}"
    
    data = await make_get_request(url, token)
    
    if not data or not data.get("success"):
        return "Unable to fetch student contract information."
    
    contract_data = data["data"]
    
    return json.dumps(contract_data, indent=2)

@mcp.tool()
async def get_student_contract_list(language: str = "en-US") -> str:
    """Get your list of contracts for all academic years from HEMIS.
    
    Args:
        language: Language for the response (e.g. en-US, uz-UZ)
    """
    token = await login_to_hemis()
    
    if not token:
        return "Unable to authenticate with HEMIS. Please check your credentials."
    
    endpoint = "student/contract-list"
    url = f"{HEMIS_API_BASE}{endpoint}?l={language}"
    
    data = await make_get_request(url, token)
    
    if not data or not data.get("success"):
        return "Unable to fetch student contract list."
    
    contract_list = data["data"].get("items", [])
    attributes = data["data"].get("attributes", {})
    
    if not contract_list:
        return "No contracts found in your student record."
    
    result = ["# Student Contracts"]
    
    contract_list.sort(key=lambda x: x.get("year", ""), reverse=True)
    
    for contract in contract_list:
        contract_year = contract.get("year", "Unknown Year")
        contract_number = contract.get("contractNumber", "Unknown")
        contract_type = contract.get("eduContractTypeName", "Unknown Type")
        
        result.append(f"\n## Contract {contract_number} ({contract_year})")
        
        result.append("\n### Education Information")
        if "eduYear" in contract and contract["eduYear"]:
            result.append(f"- Academic Year: {contract['eduYear']}")
        if "eduCourse" in contract and contract["eduCourse"]:
            result.append(f"- Level/Course: {contract['eduCourse']}")
        if "eduTypeName" in contract and contract["eduTypeName"]:
            result.append(f"- Education Type: {contract['eduTypeName']}")
        if "eduForm" in contract and contract["eduForm"]:
            result.append(f"- Education Form: {contract['eduForm']}")
        if "eduSpecialityName" in contract and contract["eduSpecialityName"]:
            result.append(f"- Specialty: {contract['eduSpecialityName']} ({contract.get('eduSpecialityCode', '')})")
        if "facultyName" in contract and contract["facultyName"]:
            result.append(f"- Faculty: {contract['facultyName']} ({contract.get('facultyCode', '')})")
        
        result.append("\n### Contract Details")
        result.append(f"- Contract Type: {contract_type}")
        if "eduContractSumTypeName" in contract and contract["eduContractSumTypeName"]:
            result.append(f"- Contract Sum Type: {contract['eduContractSumTypeName']}")
        
        result.append("\n### Financial Information")
        if "contractAmount" in contract:
            result.append(f"- Contract Amount: {contract['contractAmount']}")
        if "paidAmount" in contract:
            result.append(f"- Paid Amount: {contract['paidAmount']}")
        if "unPaidAmount" in contract:
            result.append(f"- Unpaid Amount: {contract['unPaidAmount']}")
            
        if "contractDebetAmount" in contract and contract["contractDebetAmount"]:
            result.append(f"- Contract Debt: {contract['contractDebetAmount']}")
        if "paidCreditAmount" in contract and contract["paidCreditAmount"]:
            result.append(f"- Paid Credit: {contract['paidCreditAmount']}")
        if "unPaidCreditAmount" in contract and contract["unPaidCreditAmount"]:
            result.append(f"- Unpaid Credit: {contract['unPaidCreditAmount']}")
        
        if "beginRestDebetAmount" in contract and contract["beginRestDebetAmount"]:
            result.append(f"- Debt from Previous Year: {contract['beginRestDebetAmount']}")
        if "beginRestCreditAmount" in contract and contract["beginRestCreditAmount"]:
            result.append(f"- Credit from Previous Year: {contract['beginRestCreditAmount']}")
        if "endRestDebetAmount" in contract and contract["endRestDebetAmount"]:
            result.append(f"- Current Year Debt: {contract['endRestDebetAmount']}")
        if "endRestCreditAmount" in contract and contract["endRestCreditAmount"]:
            result.append(f"- Current Year Credit: {contract['endRestCreditAmount']}")
            
        if "status" in contract:
            result.append(f"\n**Status: {contract['status']}**")
    
    return "\n".join(result)

@mcp.tool()
async def get_student_decrees(language: str = "en-US") -> str:
    """Get official orders/decrees related to you from HEMIS.
    
    Args:
        language: Language for the response (e.g. en-US, uz-UZ)
    """
    token = await login_to_hemis()
    
    if not token:
        return "Unable to authenticate with HEMIS. Please check your credentials."
    
    endpoint = "student/decree"
    url = f"{HEMIS_API_BASE}{endpoint}?l={language}"
    
    data = await make_get_request(url, token)
    
    if not data or not data.get("success"):
        return "Unable to fetch student decree information."
    
    decrees = data["data"]
    
    if not decrees:
        return "No official decrees found in your student record."
    
    result = ["# Official Student Decrees"]
    
    decrees.sort(key=lambda x: x.get("date", 0), reverse=True)
    
    for decree in decrees:
        from datetime import datetime
        
        decree_number = decree.get("number", "Unknown Number")
        decree_name = decree.get("name", "Unnamed Decree")
        
        date_ts = decree.get("date", 0)
        if date_ts:
            decree_date = datetime.fromtimestamp(date_ts).strftime('%Y-%m-%d')
        else:
            decree_date = "Date not specified"
            
        decree_type = decree.get("decreeType", {}).get("name", "Unknown Type")
        
        department = decree.get("department", {})
        department_name = department.get("name", "Unknown Department")
        department_code = department.get("code", "")
        
        file_url = decree.get("file", "")
        
        result.append(f"\n## {decree_name}")
        result.append(f"- **Decree Number:** {decree_number}")
        result.append(f"- **Date:** {decree_date}")
        result.append(f"- **Type:** {decree_type}")
        result.append(f"- **Department:** {department_name} ({department_code})")
        
        if file_url:
            result.append(f"- **Document Link:** [Download Decree]({file_url})")
    
    return "\n".join(result)
        
@mcp.tool()
async def get_student_documents(language: str = "en-US") -> str:
    """Get your official documents (diploma, transcripts, etc.) from HEMIS.
    
    Args:
        language: Language for the response (e.g. en-US, uz-UZ)
    """
    token = await login_to_hemis()
    
    if not token:
        return "Unable to authenticate with HEMIS. Please check your credentials."
    
    endpoint = "student/document"
    url = f"{HEMIS_API_BASE}{endpoint}?l={language}"
    
    data = await make_get_request(url, token)
    
    if not data or not data.get("success"):
        return "Unable to fetch student document information."
    
    documents = data["data"]
    
    if not documents:
        return "No official documents found in your student record."
    
    result = ["# Official Student Documents"]
    
    for document in documents:
        doc_name = document.get("name", "Unnamed Document")
        doc_type = document.get("type", "Unknown Type")
        doc_id = document.get("id", "")
        file_url = document.get("file", "")
        
        result.append(f"\n## {doc_name}")
        result.append(f"- **Document Type:** {doc_type}")
        
        attributes = document.get("attributes", [])
        if attributes:
            result.append("\n### Document Details")
            for attr in attributes:
                label = attr.get("label", "")
                value = attr.get("value", "")
                if label and value:
                    result.append(f"- **{label}:** {value}")
        
        if file_url:
            result.append(f"\n[Download Document]({file_url})")
    
    return "\n".join(result)

@mcp.tool()
async def get_all_student_documents(language: str = "en-US") -> str:
    """Get all your official documents (diplomas, transcripts, references, decrees, etc.) from HEMIS.
    
    Args:
        language: Language for the response (e.g. en-US, uz-UZ)
    """
    token = await login_to_hemis()
    
    if not token:
        return "Unable to authenticate with HEMIS. Please check your credentials."
    
    endpoint = "student/document-all"
    url = f"{HEMIS_API_BASE}{endpoint}?l={language}"
    
    data = await make_get_request(url, token)
    
    if not data or not data.get("success"):
        return "Unable to fetch student documents information."
    
    documents = data["data"]
    
    if not documents:
        return "No documents found in your student record."
    
    result = ["# All Student Documents"]
    
    document_types = {}
    for document in documents:
        doc_type = document.get("type", "unknown")
        if doc_type not in document_types:
            document_types[doc_type] = []
        document_types[doc_type].append(document)
    
    type_labels = {
        "diploma": "Diplomas",
        "supplement": "Diploma Supplements",
        "academic_sheet": "Academic Sheets",
        "academic_data": "Grade Books",
        "reference": "Student References",
        "decree": "Academic Orders/Decrees",
        "unknown": "Other Documents"
    }
    
    for doc_type in sorted(document_types.keys()):
        docs = document_types[doc_type]
        type_label = type_labels.get(doc_type, doc_type.title())
        result.append(f"\n## {type_label}")
        
        docs.sort(key=lambda x: x.get("id", 0), reverse=True)
        
        for document in docs:
            doc_name = document.get("name", "Unnamed Document")
            doc_id = document.get("id", "")
            file_url = document.get("file", "")
            link_url = document.get("link", "")
            
            result.append(f"\n### {doc_name}")
            
            attributes = document.get("attributes", [])
            if attributes:
                result.append("\n#### Document Details")
                for attr in attributes:
                    label = attr.get("label", "")
                    value = attr.get("value", "")
                    if label and value:
                        result.append(f"- **{label}:** {value}")
            
            if file_url:
                result.append(f"\n[Download Document]({file_url})")
            
            if link_url and link_url != file_url:
                result.append(f"\n[View Online]({link_url})")
    
    return "\n".join(result)

@mcp.tool()
async def get_student_references(language: str = "en-US") -> str:
    """Get your official student references/certificates from HEMIS.
    
    Args:
        language: Language for the response (e.g. en-US, uz-UZ)
    """
    token = await login_to_hemis()
    
    if not token:
        return "Unable to authenticate with HEMIS. Please check your credentials."
    
    endpoint = "student/reference"
    url = f"{HEMIS_API_BASE}{endpoint}?l={language}"
    
    data = await make_get_request(url, token)
    
    if not data or not data.get("success"):
        return "Unable to fetch student references."
    
    references = data["data"]
    
    if not references:
        return "No references found in your student record."
    
    result = ["# Student References"]
    
    references.sort(key=lambda x: x.get("reference_date", 0), reverse=True)
    
    for reference in references:
        from datetime import datetime
        
        ref_number = reference.get("reference_number", "Unknown Number")
        
        ref_date_ts = reference.get("reference_date", 0)
        if ref_date_ts:
            ref_date = datetime.fromtimestamp(ref_date_ts).strftime('%Y-%m-%d')
        else:
            ref_date = "Date not specified"
            
        department = reference.get("department", {})
        department_name = department.get("name", "Unknown Department")
        department_code = department.get("code", "")
        
        semester = reference.get("semester", {})
        semester_name = semester.get("name", "Unknown Semester")
        
        education_year = semester.get("education_year", {})
        year_name = education_year.get("name", "Unknown Academic Year")
        
        level = reference.get("level", {})
        level_name = level.get("name", "Unknown Level")
        
        file_url = reference.get("file", "")
        
        result.append(f"\n## Reference {ref_number}")
        result.append(f"- **Date:** {ref_date}")
        result.append(f"- **Department:** {department_name} ({department_code})")
        result.append(f"- **Academic Year:** {year_name}")
        result.append(f"- **Semester:** {semester_name}")
        result.append(f"- **Level:** {level_name}")
        
        if file_url:
            result.append(f"- **Document:** [Download Reference]({file_url})")
    
    return "\n".join(result)

@mcp.tool()
async def generate_student_reference(language: str = "en-US") -> str:
    """Generate a new student reference/certificate from HEMIS.
    
    Args:
        language: Language for the reference (e.g. en-US, uz-UZ)
    """
    token = await login_to_hemis()
    
    if not token:
        return "Unable to authenticate with HEMIS. Please check your credentials."
    
    endpoint = "student/reference-generate"
    url = f"{HEMIS_API_BASE}{endpoint}?l={language}"
    
    data = await make_get_request(url, token)
    
    if not data or not data.get("success"):
        return "Unable to generate student reference. The university might not allow automatic reference generation."
    
    reference = data["data"]
    result = ["# Student Reference Generated"]
    
    ref_number = reference.get("reference_number", "Unknown Number")
    result.append(f"\n**Reference Number:** {ref_number}")
    
    if reference.get("reference_date"):
        from datetime import datetime
        ref_date = datetime.fromtimestamp(reference["reference_date"]).strftime('%Y-%m-%d')
        result.append(f"**Date Generated:** {ref_date}")
    
    semester = reference.get("semester", {})
    semester_name = semester.get("name", "Unknown Semester")
    
    education_year = semester.get("education_year", {})
    year_name = education_year.get("name", "Unknown Academic Year")
    
    level = reference.get("level", {})
    level_name = level.get("name", "Unknown Level")
    
    department = reference.get("department", {})
    department_name = department.get("name", "Unknown Department")
    department_code = department.get("code", "")
    
    result.append(f"\n## Reference Details")
    result.append(f"- **Academic Year:** {year_name}")
    result.append(f"- **Semester:** {semester_name}")
    result.append(f"- **Level:** {level_name}")
    result.append(f"- **Department:** {department_name} ({department_code})")
    
    file_url = reference.get("file", "")
    if file_url:
        result.append(f"\n## Download")
        result.append(f"[Download Reference Document]({file_url})")
    else:
        result.append("\n**Note:** Reference document is being processed. Please check your documents list in a few minutes.")
    
    return "\n".join(result)

@mcp.tool()
async def get_student_resources(subject: str | int, semester: str | int, language: str = "en-US") -> str:
    """Get electronic resources available for a specific subject in a semester from HEMIS.
    
    Args:
        subject: Subject ID to get resources for
        semester: Semester code to get subjects for (e.g. "14" for 4th semester")
        language: Language for the response (e.g. en-US, uz-UZ)
    """
    token = await login_to_hemis()
    
    if not token:
        return "Unable to authenticate with HEMIS. Please check your credentials."
    
    endpoint = "education/resources"
    url = f"{HEMIS_API_BASE}{endpoint}?l={language}&subject={subject}&semester={semester}"
    
    data = await make_get_request(url, token)
    
    if not data or not data.get("success"):
        return "Unable to fetch resources for the specified subject and semester."
    
    resources = data["data"]
    
    if not resources:
        return "No electronic resources found for this subject in the specified semester."
    
    result = [f"# Electronic Resources for Subject #{subject} in Semester #{semester}"]
    
    resources.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
    
    for resource in resources:
        title = resource.get("title", "Untitled Resource")
        result.append(f"\n## {title}")
        
        if resource.get("comment"):
            result.append(f"\n{resource['comment']}")
        
        training_type = resource.get("trainingType", {}).get("name", "")
        if training_type:
            result.append(f"\n**Training Type:** {training_type}")
        
        employee = resource.get("employee", {}).get("name", "")
        if employee:
            result.append(f"**Instructor:** {employee}")
        
        if resource.get("updated_at"):
            from datetime import datetime
            update_date = datetime.fromtimestamp(resource["updated_at"]).strftime('%Y-%m-%d %H:%M')
            result.append(f"**Updated:** {update_date}")
        
        resource_url = resource.get("url", "")
        if resource_url:
            result.append(f"\n[Access Online Resource]({resource_url})")
        
        files = resource.get("files", [])
        if files:
            result.append("\n### Attached Files")
            for file in files:
                file_name = file.get("name", "Unnamed file")
                file_size = file.get("size", 0)
                file_url = file.get("url", "")
                
                size_display = f"{file_size} bytes"
                if file_size > 1024 * 1024:
                    size_display = f"{file_size / (1024 * 1024):.2f} MB"
                elif file_size > 1024:
                    size_display = f"{file_size / 1024:.2f} KB"
                    
                if file_url:
                    result.append(f"- [{file_name}]({file_url}) ({size_display})")
                else:
                    result.append(f"- {file_name} ({size_display})")
        
        result.append("")  # Add an empty line between resources
    
    return "\n".join(result)

@mcp.tool()
async def get_student_schedule(semester: str | int, week: str = None, language: str = "en-US") -> str:
    """Get your class schedule for a specific semester and week from HEMIS.
    
    Args:
        semester: Semester code to get subjects for (e.g. "14" for 4th semester")
        week: Week ID to get the schedule for (optional, gets current week if not specified)
        language: Language for the response (e.g. en-US, uz-UZ)
    """
    token = await login_to_hemis()
    
    if not token:
        return "Unable to authenticate with HEMIS. Please check your credentials."
    
    endpoint = "education/schedule"
    url = f"{HEMIS_API_BASE}{endpoint}?l={language}&semester={semester}"
    
    if week:
        url += f"&week={week}"
    
    data = await make_get_request(url, token)
    
    if not data or not data.get("success"):
        return "Unable to fetch schedule for the specified semester and week."
    
    schedule = data["data"]
    
    if not schedule:
        return "No schedule found for the specified semester and week."
    
    result = [f"# Class Schedule for Semester {semester}"]
    
    # Group by date and lesson pair for better organization
    from collections import defaultdict
    from datetime import datetime
    
    # Sort schedule entries by lesson date and then by lesson pair
    schedule.sort(key=lambda x: (x.get("lesson_date", 0), x.get("lessonPair", {}).get("code", "")))
    
    # Group by day
    schedule_by_day = defaultdict(list)
    
    for lesson in schedule:
        if lesson.get("lesson_date"):
            day = datetime.fromtimestamp(lesson["lesson_date"]).strftime('%Y-%m-%d')
            schedule_by_day[day].append(lesson)
    
    # Get week information if available
    if schedule and schedule[0].get("weekStartTime") and schedule[0].get("weekEndTime"):
        week_start = datetime.fromtimestamp(schedule[0]["weekStartTime"]).strftime('%Y-%m-%d')
        week_end = datetime.fromtimestamp(schedule[0]["weekEndTime"]).strftime('%Y-%m-%d')
        result.append(f"\nWeek: **{week_start}** to **{week_end}**")
    
    # Display schedule for each day
    for day, lessons in schedule_by_day.items():
        day_name = datetime.strptime(day, '%Y-%m-%d').strftime('%A')
        result.append(f"\n## {day_name} ({day})")
        
        for lesson in lessons:
            subject_info = lesson.get("subject", {})
            subject_name = subject_info.get("name", "Unknown Subject")
            subject_code = subject_info.get("code", "")
            
            lesson_pair = lesson.get("lessonPair", {})
            start_time = lesson_pair.get("start_time", "")
            end_time = lesson_pair.get("end_time", "")
            time_info = f"{start_time}-{end_time}" if start_time and end_time else "Time not specified"
            
            training_type = lesson.get("trainingType", {}).get("name", "Unknown Type")
            
            employee = lesson.get("employee", {}).get("name", "Not specified")
            
            auditorium = lesson.get("auditorium", {})
            room = auditorium.get("name", "Not specified")
            building = auditorium.get("building", {}).get("name", "")
            location = f"{room}, {building}" if building else room
            
            result.append(f"\n### {time_info} - {subject_name} ({subject_code})")
            result.append(f"- **Type:** {training_type}")
            result.append(f"- **Instructor:** {employee}")
            result.append(f"- **Location:** {location}")
            
            group = lesson.get("group", {}).get("name", "")
            if group:
                result.append(f"- **Group:** {group}")
    
    if not schedule_by_day:
        result.append("\nNo scheduled classes found for this period.")
    
    return "\n".join(result)

@mcp.tool()
async def get_subject_details(subject: str | int, semester: str | int, language: str = "en-US") -> str:
    """Get detailed information about a specific subject in your curriculum from HEMIS.
    
    Args:
        subject: Subject ID to get detailed information for
        semester: Semester code to get subjects for (e.g. "14" for 4th semester")
        language: Language for the response (e.g. en-US, uz-UZ)
    """
    token = await login_to_hemis()
    
    if not token:
        return "Unable to authenticate with HEMIS. Please check your credentials."
    
    endpoint = "education/subject"
    url = f"{HEMIS_API_BASE}{endpoint}?l={language}&semester={semester}&subject={subject}"
    
    data = await make_get_request(url, token)
    
    if not data or not data.get("success"):
        return "Unable to fetch subject details for the specified subject and semester."
    
    subject_data = data["data"]
    
    if not subject_data:
        return "No details found for this subject in the specified semester."
    
    result = []
    
    # Basic subject information
    subject_info = subject_data.get("subject", {})
    subject_name = subject_info.get("name", "Unknown Subject")
    subject_code = subject_info.get("code", "")
    subject_id = subject_info.get("id", "")
    
    result.append(f"# {subject_name} ({subject_code})")
    result.append(f"\n## General Information")
    result.append(f"- Subject ID: {subject_id}")
    
    # Subject type information
    subject_type = subject_data.get("subjectType", {})
    subject_type_name = subject_type.get("name", "Unknown Type")
    subject_type_code = subject_type.get("code", "")
    result.append(f"- Type: {subject_type_name} ({subject_type_code})")
    
    # Academic load and credit information
    total_acload = subject_data.get("total_acload", 0)
    credit = subject_data.get("credit", 0)
    result.append(f"- Total Academic Load: {total_acload} hours")
    result.append(f"- Credit Hours: {credit}")
    
    # Grading information
    max_ball = subject_data.get("max_ball", 0)
    subject_ball = subject_data.get("subject_ball", 0)
    student_ball = subject_data.get("student_ball", 0)
    
    if max_ball:
        result.append(f"\n## Grading Information")
        result.append(f"- Maximum Score: {max_ball}")
        result.append(f"- Subject Score: {subject_ball}")
        result.append(f"- Your Score: {student_ball}")
        
        if max_ball > 0 and student_ball > 0:
            percentage = (student_ball / max_ball) * 100
            result.append(f"- Percentage: {percentage:.2f}%")
    
    # Statistics
    result.append(f"\n## Activity Statistics")
    result.append(f"- Total Tasks: {subject_data.get('tasks_count', 0)}")
    result.append(f"- Submitted Tasks: {subject_data.get('submits_count', 0)}")
    result.append(f"- Marked Tasks: {subject_data.get('marked_count', 0)}")
    result.append(f"- Available Resources: {subject_data.get('resources_count', 0)}")
    result.append(f"- Absences: {subject_data.get('absent_count', 0)}")
    
    # Detailed grades if available
    grades = subject_data.get("grades", [])
    if grades:
        result.append(f"\n## Detailed Grades")
        for grade in grades:
            grade_name = grade.get("name", "Unknown Assessment")
            grade_value = grade.get("grade", 0)
            max_value = grade.get("max_ball", 0)
            
            if max_value > 0:
                percentage = (grade_value / max_value) * 100
                result.append(f"- {grade_name}: {grade_value} / {max_value} ({percentage:.2f}%)")
            else:
                result.append(f"- {grade_name}: {grade_value} / {max_value}")
    
    # Tasks if available
    tasks = subject_data.get("tasks", [])
    if tasks:
        result.append(f"\n## Tasks")
        for task in tasks:
            task_name = task.get("name", "Unnamed Task")
            result.append(f"\n### {task_name}")
            
            task_type = task.get("taskType", {}).get("name", "")
            if task_type:
                result.append(f"- Type: {task_type}")
                
            deadline = task.get("deadline")
            if deadline:
                from datetime import datetime
                deadline_date = datetime.fromtimestamp(deadline).strftime('%Y-%m-%d %H:%M')
                result.append(f"- Deadline: {deadline_date}")
                
            max_ball = task.get("max_ball")
            if max_ball is not None:
                result.append(f"- Maximum Score: {max_ball}")
                
            grade = task.get("grade")
            if grade is not None:
                result.append(f"- Your Score: {grade}")
                
                if max_ball and max_ball > 0:
                    percentage = (grade / max_ball) * 100
                    result.append(f"- Percentage: {percentage:.2f}%")
                    
            status = task.get("taskStatus", {}).get("name", "")
            if status:
                result.append(f"- Status: {status}")
    else:
        result.append("\nNo tasks have been assigned for this subject yet.")
    
    return "\n".join(result)

@mcp.tool()
async def get_student_task_list(semester: str | int, page: int = 0, limit: int = 10, language: str = "en-US") -> str:
    """Get your list of tasks/assignments for a specific semester from HEMIS.
    
    Args:
        semester: Semester code to get subjects for (e.g. "14" for 4th semester")
        page: Page number for pagination (0-based, default: 0)
        limit: Number of tasks per page (default: 10)
        language: Language for the response (e.g. en-US, uz-UZ)
    """
    token = await login_to_hemis()
    
    if not token:
        return "Unable to authenticate with HEMIS. Please check your credentials."
    
    endpoint = "education/task-list"
    url = f"{HEMIS_API_BASE}{endpoint}?l={language}&page={page}&limit={limit}&semester={semester}"
    
    data = await make_get_request(url, token)
    
    if not data or not data.get("success"):
        return "Unable to fetch tasks list for the specified semester."
    
    tasks = data["data"]
    result = [f"# Tasks List for Semester {semester}"]
    
    if not tasks:
        result.append("\nNo tasks found for this semester.")
        return "\n".join(result)
    
    # Sort tasks by deadline if available
    tasks.sort(key=lambda x: x.get("deadline", 0) or float('inf'))
    
    for task in tasks:
        task_name = task.get("name", "Unnamed Task")
        result.append(f"\n## {task_name}")
        
        if task.get("comment"):
            result.append(f"\n{task['comment']}")
        
        # Task details
        training_type = task.get("trainingType", {}).get("name", "")
        if training_type:
            result.append(f"\n- **Training Type:** {training_type}")
        
        task_type = task.get("taskType", {}).get("name", "")
        if task_type:
            result.append(f"- **Task Type:** {task_type}")
        
        max_ball = task.get("max_ball")
        if max_ball is not None:
            result.append(f"- **Maximum Score:** {max_ball}")
        
        deadline = task.get("deadline")
        if deadline:
            from datetime import datetime
            deadline_date = datetime.fromtimestamp(deadline).strftime('%Y-%m-%d %H:%M')
            result.append(f"- **Deadline:** {deadline_date}")
        
        attempt_limit = task.get("attempt_limit")
        if attempt_limit:
            result.append(f"- **Attempt Limit:** {attempt_limit}")
        
        task_status = task.get("taskStatus", {}).get("name", "")
        if task_status:
            result.append(f"- **Status:** {task_status}")
        
        employee = task.get("employee", {}).get("name", "")
        if employee:
            result.append(f"- **Instructor:** {employee}")
        
        if task.get("updated_at"):
            from datetime import datetime
            update_date = datetime.fromtimestamp(task["updated_at"]).strftime('%Y-%m-%d %H:%M')
            result.append(f"- **Last Updated:** {update_date}")
        
        # Attached files
        files = task.get("files", [])
        if files:
            result.append("\n### Attached Files")
            for file in files:
                file_name = file.get("name", "Unnamed file")
                file_size = file.get("size", 0)
                file_url = file.get("url", "")
                
                size_display = f"{file_size} bytes"
                if file_size > 1024 * 1024:
                    size_display = f"{file_size / (1024 * 1024):.2f} MB"
                elif file_size > 1024:
                    size_display = f"{file_size / 1024:.2f} KB"
                    
                if file_url:
                    result.append(f"- [{file_name}]({file_url}) ({size_display})")
                else:
                    result.append(f"- {file_name} ({size_display})")
    
    # Add pagination information
    result.append(f"\n---\n**Page {page+1}** (showing {len(tasks)} tasks)")
    result.append(f"To see more tasks, use page={page+1}")
    
    return "\n".join(result)

# ----------------------------- public -----------------------------------------

@mcp.tool()
async def get_employee_statistics(language: str = "en-US") -> str:
    """Get statistics about university employees.
    
    Args:
        language: Language for the response (e.g. en-US, uz-UZ)
    """
    endpoint = "public/stat-employee"
    url = f"{HEMIS_API_BASE}{endpoint}?l={language}"
    data = await make_get_request(url)
    
    if not data or not data.get("success"):
        return "Unable to fetch employee statistics."
    
    stats = data["data"]
    
    result = []
    
    result.append("## Position Statistics")
    for position, count in stats["position"].items():
        result.append(f"- {position}: {count}")
    
    result.append("\n## Gender Statistics")
    for gender, count in stats["gender"].items():
        result.append(f"- {gender}: {count}")
    
    result.append("\n## Citizenship Statistics")
    for citizenship, count in stats["citizenship"].items():
        result.append(f"- {citizenship}: {count}")
    
    result.append("\n## Academic Degree Statistics")
    for degree, gender_counts in stats["academic_degree"].items():
        result.append(f"- {degree}:")
        for gender, count in gender_counts.items():
            result.append(f"  - {gender}: {count}")
    
    result.append("\n## Academic Rank Statistics")
    for rank, gender_counts in stats["academic_rank"].items():
        result.append(f"- {rank}:")
        for gender, count in gender_counts.items():
            result.append(f"  - {gender}: {count}")
    
    result.append("\n## Direction Statistics")
    for direction, count in stats["direction"].items():
        result.append(f"- {direction}: {count}")
    
    result.append("\n## Academic Status")
    for status, count in stats["academic"].items():
        result.append(f"- {status}: {count}")
    
    result.append("\n## Age Statistics")
    for age_group, gender_counts in stats["age"].items():
        result.append(f"- {age_group}:")
        for gender, count in gender_counts.items():
            result.append(f"  - {gender}: {count}")
    
    result.append("\n## Employment Form Statistics")
    for form, count in stats["employment_form"].items():
        result.append(f"- {form}: {count}")

    return "\n".join(result)

@mcp.tool()
async def get_university_structure(language: str = "en-US") -> str:
    """Get statistics about university structure.
    
    Args:
        language: Language for the response (e.g. en-US, uz-UZ)
    """
    endpoint = "public/stat-structure"
    url = f"{HEMIS_API_BASE}{endpoint}?l={language}"
    data = await make_get_request(url)
    
    if not data or not data.get("success"):
        return "Unable to fetch university structure statistics."
    
    stats = data["data"]
    result = []
    
    result.append("## Student Groups Statistics")
    for degree_type, courses in stats["groups"].items():
        result.append(f"### {degree_type}")
        for course, count in courses.items():
            result.append(f"- {course}: {count} groups")
    
    result.append("\n## Auditorium Statistics")
    for item in stats["auditoriums"]:
        result.append(f"- {item['name']}: {item['count']}")
    
    result.append("\n## Specialties Statistics")
    for item in stats["specialities"]:
        result.append(f"- {item['name']}: {item['count']}")
    
    result.append("\n## Department Statistics")
    for item in stats["departments"]:
        result.append(f"- {item['name']}: {item['count']}")
    
    return "\n".join(result)

@mcp.tool()
async def get_student_statistics(language: str = "en-US") -> str:
    """Get statistics about university students.
    
    Args:
        language: Language for the response (e.g. en-US, uz-UZ)
    """
    endpoint = "public/stat-student"
    url = f"{HEMIS_API_BASE}{endpoint}?l={language}"
    data = await make_get_request(url)
    
    if not data or not data.get("success"):
        return "Unable to fetch student statistics."
    
    stats = data["data"]
    result = []
    
    result.append("## Education Type Statistics")
    for edu_type, gender_counts in stats["education_type"].items():
        result.append(f"### {edu_type}")
        for gender, count in gender_counts.items():
            result.append(f"- {gender}: {count}")
    
    result.append("\n## Age Statistics")
    for edu_level, age_groups in stats["age"].items():
        result.append(f"### {edu_level}")
        for age_group, gender_counts in age_groups.items():
            result.append(f"#### {age_group}")
            for gender, count in gender_counts.items():
                result.append(f"- {gender}: {count}")
    
    result.append("\n## Payment Type Statistics")
    for payment_type, edu_counts in stats["payment"].items():
        result.append(f"### {payment_type}")
        for edu_level, count in edu_counts.items():
            result.append(f"- {edu_level}: {count}")
    
    result.append("\n## Regional Statistics")
    for region, edu_counts in stats["region"].items():
        result.append(f"### {region}")
        for edu_level, count in edu_counts.items():
            result.append(f"- {edu_level}: {count}")
    
    result.append("\n## Citizenship Statistics")
    for citizenship, edu_counts in stats["citizenship"].items():
        result.append(f"### {citizenship}")
        for edu_level, count in edu_counts.items():
            result.append(f"- {edu_level}: {count}")
    
    result.append("\n## Accommodation Statistics")
    for accommodation, edu_counts in stats["accommodation"].items():
        result.append(f"### {accommodation}")
        for edu_level, count in edu_counts.items():
            result.append(f"- {edu_level}: {count}")
    
    result.append("\n## Education Form Statistics")
    for edu_level, forms in stats["education_form"].items():
        result.append(f"### {edu_level}")
        for form, gender_counts in forms.items():
            result.append(f"#### {form}")
            for gender, count in gender_counts.items():
                result.append(f"- {gender}: {count}")
    
    result.append("\n## Student Level Statistics")
    for edu_level, courses in stats["level"].items():
        result.append(f"### {edu_level}")
        for course, forms in courses.items():
            result.append(f"#### {course}")
            for form, count in forms.items():
                if count > 0:  # Only show forms with students
                    result.append(f"- {form}: {count}")
    
    return "\n".join(result)

@mcp.tool()
async def get_universities(language: str = "en-US") -> str:
    """Get a list of universities using HEMIS system.
    
    Args:
        language: Language for the response (e.g. en-US, uz-UZ)
    """
    endpoint = "public/universities"
    url = f"{HEMIS_API_BASE}{endpoint}?l={language}"
    data = await make_get_request(url)
    
    if not data or not data.get("success"):
        return "Unable to fetch universities list."
    
    universities = data["data"]
    result = ["# Universities using HEMIS system"]
    
    for university in universities:
        result.append(f"\n## {university['name']}")
        result.append(f"- University Type: {university['university_type']}")
    
    return "\n".join(result)

@mcp.tool()
async def get_university_profile(language: str = "en-US") -> str:
    """Get profile information about university.
    
    Args:
        language: Language for the response (e.g. en-US, uz-UZ)
    """
    endpoint = "public/university-profile"
    url = f"{HEMIS_API_BASE}{endpoint}?l={language}"
    data = await make_get_request(url)
    
    if not data or not data.get("success"):
        return "Unable to fetch university profile information."
    
    profile = data["data"]
    result = []
    
    result.append(f"# {profile['name']}")
    
    result.append("\n## General Information")
    result.append(f"- Contact: {profile['contact']}")
    result.append(f"- Address: {profile['address']}")
    result.append(f"- Mailing Address: {profile['mailing_address']}")
    
    result.append("\n## University Details")
    result.append(f"- Region: {profile['soato']['name']}")
    result.append(f"- Ownership Type: {profile['ownership']['name']}")
    
    return "\n".join(result)


if __name__ == "__main__":
    mcp.run(transport='stdio')