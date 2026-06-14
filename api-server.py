from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from main import start_attendance_system
import threading
import mysql.connector
from pydantic import BaseModel


# ─── DB Connection Helper ─────────────────────────────────────────────────────

def get_connection():
    """Creates and returns a fresh MySQL connection."""
    return mysql.connector.connect(
        host     = 'localhost',
        user     = 'root',
        password = 'root',
        database = 'STUDENTS'
    )


# ─── Models ───────────────────────────────────────────────────────────────────

class LoginData(BaseModel):
    username: str
    password: str
    role: str


class SessionData(BaseModel):
    program: str
    duration: int


class AttendanceUpdateData(BaseModel):
    roll: str
    date: str
    status: str


class CandidateData(BaseModel):
    name: str
    roll: str
    program: str


# ─── App Setup ────────────────────────────────────────────────────────────────

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.post("/login")
def login(data: LoginData):
    role = data.role.lower()

    if role not in ("admin", "teacher", "student"):
        raise HTTPException(status_code=400, detail="Invalid role selected.")

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        # Look up user by username AND role together
        cursor.execute(
            "SELECT * FROM USERS WHERE USERNAME = %s AND ROLE = %s;",
            (data.username.lower(), role)
        )
        user = cursor.fetchone()

    except mysql.connector.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    finally:
        cursor.close()
        connection.close()

    # User not found for that role
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    # Check password
    if user["PASSWORD"] != data.password:
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    return {"message": "Login successful", "role": role, "username": user["USERNAME"]}


@app.post("/start-attendance")
def start_attendance(data: SessionData):
    thread = threading.Thread(
        target=start_attendance_system,
        args=(data.program, data.duration, True)   
    )
    thread.daemon = True
    thread.start()
    return {"message": f"Attendance started for {data.program} ({data.duration} mins)"}

@app.post("/update-attendance")
def update_attendance(data: AttendanceUpdateData):
    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute(
            "UPDATE STUDENT_INFO SET STATUS = %s WHERE NAME = %s AND TIME LIKE %s;",
            (data.status, data.roll, f"%{data.date}%")
        )
        connection.commit()

        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="No matching attendance record found.")

    except mysql.connector.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    finally:
        cursor.close()
        connection.close()

    return {"message": f"Attendance updated for {data.roll} on {data.date} → {data.status}"}


@app.post("/update-candidate")
def update_candidate(data: CandidateData):
    try:
        connection = get_connection()
        cursor = connection.cursor()

        # Insert new candidate record
        cursor.execute(
            "INSERT INTO STUDENT_INFO (NAME, TIME, STATUS) VALUES (%s, %s, %s);",
            (data.name, data.roll, 'PRESENT')
        )
        connection.commit()

    except mysql.connector.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    finally:
        cursor.close()
        connection.close()

    return {"message": f"Candidate {data.name} (Roll: {data.roll}) added successfully"}

@app.get("/student/attendance")
def get_student_attendance(username: str):
    """
    Returns all attendance records for the given student.
    Matches by NAME column in STUDENT_INFO.
    """
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        # First get the student's real name from USERS table
        cursor.execute(
            "SELECT * FROM STUDENT_INFO WHERE NAME = %s;",
            (username.lower(),)
        )
        user = cursor.fetchone()

        if user is None:
            raise HTTPException(status_code=404, detail="Student not found.")

        # Fetch all attendance rows matching their name
        cursor.execute(
            "SELECT NAME, TIME, STATUS FROM STUDENT_INFO WHERE NAME = %s ORDER BY TIME DESC;",
            (user["USERNAME"],)
        )
        records = cursor.fetchall()

    except mysql.connector.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        cursor.close()
        connection.close()

    return {"records": records}


@app.get("/student/profile")
def get_student_profile(username: str):
    """
    Returns profile info for the given student.
    """
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        # Get user info from USERS table
        cursor.execute(
            "SELECT USERNAME, ROLL, PROGRAM FROM USERS WHERE USERNAME = %s AND ROLE = 'student';",
            (username.lower(),)
        )
        user = cursor.fetchone()

        if user is None:
            raise HTTPException(status_code=404, detail="Student not found.")

        # Count total sessions attended
        cursor.execute(
            "SELECT COUNT(*) as total FROM STUDENT_INFO WHERE NAME = %s;",
            (user["USERNAME"],)
        )
        count = cursor.fetchone()

    except mysql.connector.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        cursor.close()
        connection.close()

    return {
        "username":       user["USERNAME"],
        "name":           user["USERNAME"],   # replace with NAME column if you add one
        "roll":           user.get("ROLL", "—"),
        "program":        user.get("PROGRAM", "—"),
        "total_sessions": count["total"] if count else 0
    }
