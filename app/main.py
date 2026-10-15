"""
Employee Attendance & Analytics API - STARTER

Run:  uvicorn app.main:app --port 8000
Env:  MONGO_URI, MONGO_DB (a local .env is loaded for convenience)

This file was written quickly by a colleague who has left the company. The happy path
works, but nobody has reviewed it. Read PROBLEM_STATEMENT.docx for what is expected of you,
openapi.yaml for the contract and DATA_MODEL.md for what is stored in MongoDB.
"""





from datetime import datetime, timedelta
import os
import re
import calendar
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Path
from pydantic import BaseModel, ConfigDict, Field, EmailStr
from pymongo import MongoClient, ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "employee_attendance")

UTC = timezone.utc
IST = timezone(timedelta(hours=5, minutes=30))

app = FastAPI(
    title="Employee Attendance & Analytics API",
    version="1.0.0",
)

client = MongoClient(
    MONGO_URI,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
    socketTimeoutMS=10000,
)

db = client[MONGO_DB]
employees = db["employees"]
attendance = db["attendance_logs"]


# ---------------------------------------------------------
# Common helpers
# ---------------------------------------------------------

def utc_now_seconds() -> datetime:
    """Return a timezone-aware UTC datetime truncated to seconds."""
    return datetime.now(UTC).replace(microsecond=0)


def as_utc_seconds(value: datetime) -> datetime:
    """Normalize a datetime to UTC and truncate to whole seconds."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).replace(microsecond=0)


def epoch_ms_to_utc(value: int) -> datetime:
    """Convert an integer epoch-millisecond timestamp to UTC."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise HTTPException(
            status_code=422,
            detail="Timestamp must be an integer epoch-millisecond value.",
        )

    if value < 100_000_000_000:
        raise HTTPException(
            status_code=422,
            detail="Timestamp must be in milliseconds, not seconds.",
        )

    try:
        result = datetime.fromtimestamp(value / 1000, tz=UTC)
    except (ValueError, OverflowError, OSError):
        raise HTTPException(status_code=422, detail="Invalid timestamp.")

    return result.replace(microsecond=0)


def to_epoch_ms(value: Optional[datetime]) -> Optional[int]:
    """Convert a MongoDB datetime to integer epoch milliseconds."""
    if value is None:
        return None

    value = as_utc_seconds(value)
    return int(value.timestamp() * 1000)


def round_half_up(value: float, places: int = 2) -> float:
    quantum = Decimal("1").scaleb(-places)
    return float(
        Decimal(str(value)).quantize(
            quantum,
            rounding=ROUND_HALF_UP,
        )
    )


def parse_calendar_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=422,
            detail="Date must use YYYY-MM-DD format.",
        )


def parse_month(value: str) -> tuple[date, date]:
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
        raise HTTPException(
            status_code=422,
            detail="Month must use YYYY-MM format.",
        )

    try:
        year, month = map(int, value.split("-"))
        first = date(year, month, 1)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid month.")

    last = date(year, month, calendar.monthrange(year, month)[1])
    return first, last


def parse_hhmm(value: str) -> time:
    if not isinstance(value, str) or not re.fullmatch(
        r"(?:[01]\d|2[0-3]):[0-5]\d", value
    ):
        raise HTTPException(
            status_code=422,
            detail="Time must use HH:MM format.",
        )

    hour, minute = map(int, value.split(":"))
    return time(hour, minute)


def shift_is_overnight(shift_start: str, shift_end: str) -> bool:
    return parse_hhmm(shift_end) <= parse_hhmm(shift_start)


def attendance_date_for(
    punch_in_utc: datetime,
    shift_start: str,
    shift_end: str,
) -> date:
    local_dt = as_utc_seconds(punch_in_utc).astimezone(IST)
    local_date = local_dt.date()
    local_time = local_dt.time().replace(tzinfo=None)

    if shift_is_overnight(shift_start, shift_end):
        if local_time < parse_hhmm(shift_end):
            return local_date - timedelta(days=1)

    return local_date


def shift_start_datetime(day: date, shift_start: str) -> datetime:
    local = datetime.combine(day, parse_hhmm(shift_start), tzinfo=IST)
    return local.astimezone(UTC).replace(microsecond=0)


def shift_end_datetime(day: date, shift_start: str, shift_end: str) -> datetime:
    start = parse_hhmm(shift_start)
    end = parse_hhmm(shift_end)

    end_day = day
    if end <= start:
        end_day += timedelta(days=1)

    local = datetime.combine(end_day, end, tzinfo=IST)
    return local.astimezone(UTC).replace(microsecond=0)


def calculate_late_minutes(
    punch_in: datetime,
    attendance_day: date,
    shift_start: str,
) -> int:
    punch_in = as_utc_seconds(punch_in)
    scheduled_start = shift_start_datetime(attendance_day, shift_start)

    elapsed_seconds = int((punch_in - scheduled_start).total_seconds())

    # Late only when strictly more than 10 minutes late.
    if elapsed_seconds <= 600:
        return 0

    # Count full elapsed minutes from scheduled shift start.
    return max(0, elapsed_seconds // 60)


def calculate_overtime_minutes(
    punch_out: datetime,
    attendance_day: date,
    shift_start: str,
    shift_end: str,
) -> int:
    punch_out = as_utc_seconds(punch_out)
    scheduled_end = shift_end_datetime(
        attendance_day,
        shift_start,
        shift_end,
    )

    elapsed_seconds = int((punch_out - scheduled_end).total_seconds())

    # Overtime is recorded only when at least 30 minutes are completed.
    if elapsed_seconds < 1800:
        return 0

    return elapsed_seconds // 60


def calculate_work_hours(
    punch_in: datetime,
    punch_out: datetime,
) -> float:
    seconds = (
        as_utc_seconds(punch_out) - as_utc_seconds(punch_in)
    ).total_seconds()

    return round_half_up(seconds / 3600, 2)


def is_weekday(day: date) -> bool:
    return day.weekday() < 5


def working_days_count(start: date, end: date) -> int:
    """Count Monday-Friday days, inclusive."""
    if start > end:
        return 0

    total = 0
    current = start

    while current <= end:
        if is_weekday(current):
            total += 1
        current += timedelta(days=1)

    return total


def employee_response(document: dict) -> dict:
    result = dict(document)
    result.pop("_id", None)

    if isinstance(result.get("created_at"), datetime):
        result["created_at"] = to_epoch_ms(result["created_at"])

    return result


def attendance_response(document: dict) -> dict:
    result = dict(document)
    result.pop("_id", None)

    for field in ("punch_in", "punch_out"):
        if isinstance(result.get(field), datetime):
            result[field] = to_epoch_ms(result[field])

    history = result.get("history", [])
    converted_history = []

    for entry in history:
        item = dict(entry)

        if isinstance(item.get("at"), datetime):
            item["at"] = to_epoch_ms(item["at"])

        changes = item.get("changes", {})
        converted_changes = {}

        for field, change in changes.items():
            converted_change = dict(change)

            for side in ("from", "to"):
                if isinstance(converted_change.get(side), datetime):
                    converted_change[side] = to_epoch_ms(
                        converted_change[side]
                    )

            converted_changes[field] = converted_change

        item["changes"] = converted_changes
        converted_history.append(item)

    result["history"] = converted_history
    result.setdefault("late_minutes", 0)
    result.setdefault("overtime_minutes", 0)
    result.setdefault("half_day", False)

    return result


def get_employee(emp_code: str) -> dict:
    employee = employees.find_one({"emp_code": emp_code})

    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found.")

    return employee


def get_attendance(emp_code: str, attendance_day: date) -> Optional[dict]:
    return attendance.find_one(
        {
            "emp_code": emp_code,
            "date": attendance_day.isoformat(),
        }
    )


def pagination_values(page: int, page_size: int) -> tuple[int, int]:
    if page < 1:
        raise HTTPException(status_code=422, detail="page must be >= 1.")

    if page_size < 1 or page_size > 100:
        raise HTTPException(
            status_code=422,
            detail="page_size must be between 1 and 100.",
        )

    return (page - 1) * page_size, page_size


# ---------------------------------------------------------
# Request models
# ---------------------------------------------------------

class EmployeeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    emp_code: str = Field(pattern=r"^EMP\d{4,6}$")
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    department: str = Field(min_length=1, max_length=100)
    shift_start: str
    shift_end: str
    joined_on: str


class PunchInRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    emp_code: str
    punched_at: Optional[int] = None


class PunchOutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    emp_code: str
    punched_at: Optional[int] = None


class AttendanceCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Optional[str] = None
    punch_in: Optional[int] = None
    punch_out: Optional[int] = None
    reason: str = Field(min_length=1, max_length=500)
    by: str = Field(min_length=1, max_length=100)


# ---------------------------------------------------------
# Startup and health
# ---------------------------------------------------------

@app.on_event("startup")
def startup() -> None:
    employees.create_index(
        [("emp_code", ASCENDING)],
        unique=True,
        name="uq_employees_emp_code",
    )

    employees.create_index(
        [("department", ASCENDING), ("joined_on", ASCENDING)],
        name="ix_employees_department_joined",
    )

    attendance.create_index(
        [("emp_code", ASCENDING), ("date", ASCENDING)],
        unique=True,
        name="uq_attendance_emp_date",
    )

    attendance.create_index(
        [("date", DESCENDING), ("emp_code", ASCENDING)],
        name="ix_attendance_date_emp",
    )

    attendance.create_index(
        [
            ("status", ASCENDING),
            ("date", DESCENDING),
            ("emp_code", ASCENDING),
        ],
        name="ix_attendance_status_date_emp",
    )

    attendance.create_index(
        [("punch_in", DESCENDING)],
        name="ix_attendance_punch_in",
    )


@app.get("/health")
def health() -> dict:
    try:
        client.admin.command("ping")
        return {"status": "ok"}
    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="MongoDB is unavailable.",
        )


# ---------------------------------------------------------
# Employee endpoints
# ---------------------------------------------------------

@app.post("/employees", status_code=201)
def create_employee(payload: EmployeeCreate) -> dict:
    parse_hhmm(payload.shift_start)
    parse_hhmm(payload.shift_end)
    joined_on = parse_calendar_date(payload.joined_on)

    document = {
        "emp_code": payload.emp_code,
        "name": payload.name.strip(),
        "email": str(payload.email),
        "department": payload.department.strip(),
        "shift_start": payload.shift_start,
        "shift_end": payload.shift_end,
        "joined_on": joined_on.isoformat(),
        "created_at": utc_now_seconds(),
    }

    if not document["name"] or not document["department"]:
        raise HTTPException(
            status_code=422,
            detail="Name and department cannot be blank.",
        )

    try:
        employees.insert_one(document)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=409,
            detail="Employee code already exists.",
        )

    return employee_response(document)


@app.get("/employees")
def list_employees(
    department: Optional[str] = None,
    joined_from: Optional[str] = None,
    joined_to: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    skip, limit = pagination_values(page, page_size)
    query: dict[str, Any] = {}

    if department is not None:
        query["department"] = department

    if joined_from is not None or joined_to is not None:
        joined_filter: dict[str, str] = {}

        if joined_from is not None:
            parse_calendar_date(joined_from)
            joined_filter["$gte"] = joined_from

        if joined_to is not None:
            parse_calendar_date(joined_to)
            joined_filter["$lte"] = joined_to

        query["joined_on"] = joined_filter

    total = employees.count_documents(query)

    cursor = (
        employees.find(query, {"_id": 0})
        .sort("emp_code", ASCENDING)
        .skip(skip)
        .limit(limit)
    )

    items = [employee_response(item) for item in cursor]

    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
    }


# ---------------------------------------------------------
# Punch-in and punch-out
# ---------------------------------------------------------

@app.post("/attendance/punch-in", status_code=201)
def punch_in(payload: PunchInRequest) -> dict:
    employee = get_employee(payload.emp_code)

    if payload.punched_at is None:
        punch_time = utc_now_seconds()
    else:
        punch_time = epoch_ms_to_utc(payload.punched_at)

    day = attendance_date_for(
        punch_time,
        employee["shift_start"],
        employee["shift_end"],
    )

    if day < parse_calendar_date(employee["joined_on"]):
        raise HTTPException(
            status_code=422,
            detail="Attendance date is before the employee joining date.",
        )

    document = {
        "emp_code": payload.emp_code,
        "date": day.isoformat(),
        "status": "PRESENT",
        "punch_in": punch_time,
        "punch_out": None,
        "work_hours": None,
        "late_minutes": calculate_late_minutes(
            punch_time,
            day,
            employee["shift_start"],
        ),
        "overtime_minutes": 0,
        "half_day": False,
        "history": [],
    }

    try:
        attendance.insert_one(document)
    except DuplicateKeyError:
        existing = get_attendance(payload.emp_code, day)

        if existing is not None and existing.get("punch_in") is not None:
            raise HTTPException(
                status_code=409,
                detail="Attendance or punch-in already exists for this date.",
            )

        raise HTTPException(
            status_code=409,
            detail="Attendance record already exists for this date.",
        )

    return attendance_response(document)


@app.post("/attendance/punch-out")
def punch_out(payload: PunchOutRequest) -> dict:
    employee = get_employee(payload.emp_code)

    if payload.punched_at is None:
        punch_time = utc_now_seconds()
    else:
        punch_time = epoch_ms_to_utc(payload.punched_at)

    open_record = attendance.find_one(
        {
            "emp_code": payload.emp_code,
            "punch_in": {"$ne": None, "$lte": punch_time},
            "punch_out": None,
        },
        sort=[("punch_in", DESCENDING)],
    )

    if open_record is None:
        raise HTTPException(
            status_code=404,
            detail="No open attendance record found for punch-out.",
        )

    punch_start = as_utc_seconds(open_record["punch_in"])
    punch_time = as_utc_seconds(punch_time)

    if punch_time < punch_start:
        raise HTTPException(
            status_code=422,
            detail="Punch-out cannot be earlier than punch-in.",
        )

    if punch_time - punch_start > timedelta(hours=24):
        raise HTTPException(
            status_code=422,
            detail="Punch-out cannot be more than 24 hours after punch-in.",
        )

    day = parse_calendar_date(open_record["date"])

    work_hours = calculate_work_hours(punch_start, punch_time)
    half_day = work_hours < 4.50

    overtime = calculate_overtime_minutes(
        punch_time,
        day,
        employee["shift_start"],
        employee["shift_end"],
    )

    updated = attendance.find_one_and_update(
        {
            "_id": open_record["_id"],
            "punch_out": None,
        },
        {
            "$set": {
                "punch_out": punch_time,
                "work_hours": work_hours,
                "half_day": half_day,
                "overtime_minutes": overtime,
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    if updated is None:
        raise HTTPException(
            status_code=409,
            detail="Attendance record was updated concurrently.",
        )

    return attendance_response(updated)


# ---------------------------------------------------------
# Attendance list
# ---------------------------------------------------------

@app.get("/attendance")
def list_attendance(
    emp_code: Optional[str] = None,
    department: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    skip, limit = pagination_values(page, page_size)
    query: dict[str, Any] = {}

    if emp_code is not None:
        query["emp_code"] = emp_code

    if status is not None:
        allowed_statuses = {
            "PRESENT",
            "ABSENT",
            "LEAVE",
            "WFH",
            "ON_DUTY",
        }

        if status not in allowed_statuses:
            raise HTTPException(
                status_code=422,
                detail="Unsupported attendance status.",
            )

        query["status"] = status

    if date_from is not None or date_to is not None:
        date_filter: dict[str, str] = {}

        if date_from is not None:
            parse_calendar_date(date_from)
            date_filter["$gte"] = date_from

        if date_to is not None:
            parse_calendar_date(date_to)
            date_filter["$lte"] = date_to

        query["date"] = date_filter

    if department is not None:
        matching_employees = employees.find(
            {"department": department},
            {"_id": 0, "emp_code": 1},
        )
        employee_codes = [item["emp_code"] for item in matching_employees]
        query["emp_code"] = {"$in": employee_codes}

    total = attendance.count_documents(query)

    cursor = (
        attendance.find(query)
        .sort([("date", DESCENDING), ("emp_code", ASCENDING)])
        .skip(skip)
        .limit(limit)
    )

    return {
        "items": [attendance_response(item) for item in cursor],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


# ---------------------------------------------------------
# Manual attendance correction
# ---------------------------------------------------------




@app.patch("/attendance/{emp_code}/{date}")
def correct_attendance(
    emp_code: str,
    date: str,
    payload: AttendanceCorrection,
) -> dict:
    employee = get_employee(emp_code)
    day = parse_calendar_date(date)

    if day < parse_calendar_date(employee["joined_on"]):
        raise HTTPException(
            status_code=422,
            detail="Attendance date is before the joining date.",
        )

    record = get_attendance(emp_code, day)

    if record is None:
        raise HTTPException(
            status_code=404,
            detail="Attendance record not found.",
        )

    # 1. Collect requested updates.
    updates: dict[str, Any] = {}

    if payload.status is not None:
        allowed_statuses = {
            "PRESENT",
            "ABSENT",
            "LEAVE",
            "WFH",
            "ON_DUTY",
        }

        if payload.status not in allowed_statuses:
            raise HTTPException(
                status_code=422,
                detail="Unsupported attendance status.",
            )

        updates["status"] = payload.status

    if payload.punch_in is not None:
        updates["punch_in"] = epoch_ms_to_utc(payload.punch_in)

    if payload.punch_out is not None:
        updates["punch_out"] = epoch_ms_to_utc(payload.punch_out)

    # 2. Calculate the effective values after the requested update.
    new_punch_in = updates.get(
        "punch_in",
        record.get("punch_in"),
    )
    new_punch_out = updates.get(
        "punch_out",
        record.get("punch_out"),
    )
    new_status = updates.get(
        "status",
        record.get("status"),
    )

    # 3. Validate punch timestamps.
    if new_punch_in is not None and new_punch_out is not None:
        if as_utc_seconds(new_punch_out) < as_utc_seconds(new_punch_in):
            raise HTTPException(
                status_code=422,
                detail="Punch-out cannot be earlier than punch-in.",
            )

        if (
            as_utc_seconds(new_punch_out)
            - as_utc_seconds(new_punch_in)
            > timedelta(hours=24)
        ):
            raise HTTPException(
                status_code=422,
                detail="Punch-out cannot be more than 24 hours after punch-in.",
            )

    # 4. Recalculate derived attendance fields.
    if new_status in {"ABSENT", "LEAVE"}:
        updates.update(
            {
                "punch_in": None,
                "punch_out": None,
                "work_hours": None,
                "late_minutes": 0,
                "overtime_minutes": 0,
                "half_day": False,
            }
        )

    elif new_punch_in is not None:
        updates["late_minutes"] = calculate_late_minutes(
            new_punch_in,
            day,
            employee["shift_start"],
        )

        if new_punch_out is not None:
            work_hours = calculate_work_hours(
                new_punch_in,
                new_punch_out,
            )

            updates["work_hours"] = work_hours
            updates["half_day"] = work_hours < 4.50
            updates["overtime_minutes"] = calculate_overtime_minutes(
                new_punch_out,
                day,
                employee["shift_start"],
                employee["shift_end"],
            )
        else:
            updates["work_hours"] = None
            updates["half_day"] = False
            updates["overtime_minutes"] = 0

    # 5. Compare old and new values.
    # IMPORTANT: Initialize changes before entering the loop.
    changes: dict[str, Any] = {}

    for field, new_value in updates.items():
        old_value = record.get(field)

        if field in {"punch_in", "punch_out"}:
            if old_value is None or new_value is None:
                values_equal = old_value is new_value
            else:
                values_equal = (
                    as_utc_seconds(old_value)
                    == as_utc_seconds(new_value)
                )
        else:
            values_equal = old_value == new_value

        if not values_equal:
            changes[field] = {
                "from": old_value,
                "to": new_value,
            }


      # 6. Reject a correction when no fields change.
    if not changes:
        raise HTTPException(
            status_code=422,
            detail="No changes detected in the attendance correction.",
        )


    # 7. Create an audit-history entry.
    history_entry = {
        "at": utc_now_seconds(),
        "by": payload.by,
        "reason": payload.reason,
        "changes": changes,
    }

    # 8. Save the update with a concurrency check.
    updated = attendance.find_one_and_update(
        {
            "_id": record["_id"],
            "history": record.get("history", []),
        },
        {
            "$set": updates,
            "$push": {
                "history": history_entry,
            },
        },
        return_document=ReturnDocument.AFTER,
    )

    if updated is None:
        raise HTTPException(
            status_code=409,
            detail="Attendance record changed concurrently; retry the request.",
        )

    # 9. Return the updated attendance record.
    return attendance_response(updated)


# ---------------------------------------------------------
# Monthly employee analytics
# ---------------------------------------------------------

@app.get("/analytics/employees/{emp_code}/monthly")
def employee_monthly_analytics(
    emp_code: str,
    month: str,
) -> dict:
    employee = get_employee(emp_code)
    first_day, last_day = parse_month(month)

    joined_on = parse_calendar_date(employee["joined_on"])
    effective_start = max(first_day, joined_on)

    working_days = working_days_count(effective_start, last_day)

    pipeline = [
        {
            "$match": {
                "emp_code": emp_code,
                "date": {
                    "$gte": first_day.isoformat(),
                    "$lte": last_day.isoformat(),
                },
            }
        },
        {
            "$addFields": {
                "_date": {
                    "$dateFromString": {
                        "dateString": "$date",
                        "format": "%Y-%m-%d",
                    }
                }
            }
        },
        {
            "$addFields": {
                "_weekday": {
                    "$dayOfWeek": "$_date",
                }
            }
        },
        {
            "$group": {
                "_id": None,
                "present_days": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    {"$in": ["$status", ["PRESENT", "WFH", "ON_DUTY"]]},
                                    {"$in": ["$_weekday", [2, 3, 4, 5, 6]]},
                                ]
                            },
                            {
                                "$cond": [
                                    "$half_day",
                                    0.5,
                                    1.0,
                                ]
                            },
                            0,
                        ]
                    }
                },
                "leave_days": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$status", "LEAVE"]},
                            1,
                            0,
                        ]
                    }
                },
                "late_count": {
                    "$sum": {
                        "$cond": [
                            {"$gt": ["$late_minutes", 0]},
                            1,
                            0,
                        ]
                    }
                },
                "total_late_minutes": {
                    "$sum": {"$ifNull": ["$late_minutes", 0]}
                },
                "total_overtime_minutes": {
                    "$sum": {"$ifNull": ["$overtime_minutes", 0]}
                },
            }
        },
    ]

    rows = list(attendance.aggregate(pipeline))
    metrics = rows[0] if rows else {}

    present_days = float(metrics.get("present_days", 0))
    attendance_pct = (
        round_half_up((present_days / working_days) * 100, 4)
        if working_days
        else 0.0
    )

    return {
        "emp_code": emp_code,
        "month": month,
        "working_days": working_days,
        "present_days": round_half_up(present_days, 2),
        "leave_days": metrics.get("leave_days", 0),
        "late_count": metrics.get("late_count", 0),
        "total_late_minutes": metrics.get("total_late_minutes", 0),
        "total_overtime_minutes": metrics.get("total_overtime_minutes", 0),
        "attendance_pct": attendance_pct,
    }


# ---------------------------------------------------------
# Department summary analytics
# ---------------------------------------------------------

@app.get("/analytics/departments/summary")
def department_summary(
    month: str,
) -> dict:
    first_day, last_day = parse_month(month)
    end_string = last_day.isoformat()

    pipeline = [
        {
            "$match": {
                "joined_on": {"$lte": end_string},
            }
        },
        {
            "$lookup": {
                "from": "attendance_logs",
                "let": {
                    "employee_code": "$emp_code",
                    "joined": "$joined_on",
                },
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$emp_code", "$$employee_code"]},
                                    {"$gte": ["$date", first_day.isoformat()]},
                                    {"$lte": ["$date", end_string]},
                                    {"$gte": ["$date", "$$joined"]},
                                ]
                            }
                        }
                    }
                ],
                "as": "logs",
            }
        },
        {
            "$unwind": {
                "path": "$logs",
                "preserveNullAndEmptyArrays": True,
            }
        },
        {
            "$addFields": {
                "_weekday": {
                    "$cond": [
                        {"$ne": ["$logs", None]},
                        {
                            "$dayOfWeek": {
                                "$dateFromString": {
                                    "dateString": "$logs.date",
                                    "format": "%Y-%m-%d",
                                }
                            }
                        },
                        None,
                    ]
                }
            }
        },
        {
            "$group": {
                "_id": "$department",
                "_employees": {"$addToSet": "$emp_code"},
                "present_days": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    {"$ne": ["$logs", None]},
                                    {"$in": ["$logs.status", ["PRESENT", "WFH", "ON_DUTY"]]},
                                    {"$in": ["$_weekday", [2, 3, 4, 5, 6]]},
                                ]
                            },
                            {
                                "$cond": [
                                    "$logs.half_day",
                                    0.5,
                                    1.0,
                                ]
                            },
                            0,
                        ]
                    }
                },
                "leave_count": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$logs.status", "LEAVE"]},
                            1,
                            0,
                        ]
                    }
                },
                "late_count": {
                    "$sum": {
                        "$cond": [
                            {"$gt": ["$logs.late_minutes", 0]},
                            1,
                            0,
                        ]
                    }
                },
                "total_late_minutes": {
                    "$sum": {"$ifNull": ["$logs.late_minutes", 0]}
                },
                "total_overtime_minutes": {
                    "$sum": {"$ifNull": ["$logs.overtime_minutes", 0]}
                },
                "work_hour_sum": {
                    "$sum": {"$ifNull": ["$logs.work_hours", 0]}
                },
                "work_hour_count": {
                    "$sum": {
                        "$cond": [
                            {"$ne": ["$logs.work_hours", None]},
                            1,
                            0,
                        ]
                    }
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "department": "$_id",
                "headcount": {"$size": "$_employees"},
                "present_days": {"$round": ["$present_days", 2]},
                "leave_count": 1,
                "late_count": 1,
                "total_late_minutes": 1,
                "total_overtime_minutes": 1,
                "average_work_hours": {
                    "$cond": [
                        {"$gt": ["$work_hour_count", 0]},
                        {
                            "$round": [
                                {
                                    "$divide": [
                                        "$work_hour_sum",
                                        "$work_hour_count",
                                    ]
                                },
                                2,
                            ]
                        },
                        None,
                    ]
                },
            }
        },
        {"$sort": {"department": 1}},
    ]

    rows = list(employees.aggregate(pipeline))

    return {
        "month": month,
        "departments": rows,
    }


# ---------------------------------------------------------
# Late-arrival leaderboard
# ---------------------------------------------------------

@app.get("/analytics/leaderboard/late")
def late_leaderboard(
    month: str,
    limit: int = Query(10, ge=1, le=100),
) -> dict:
    first_day, last_day = parse_month(month)

    pipeline = [
        {
            "$match": {
                "date": {
                    "$gte": first_day.isoformat(),
                    "$lte": last_day.isoformat(),
                },
                "late_minutes": {"$gt": 0},
            }
        },
        {
            "$group": {
                "_id": "$emp_code",
                "late_count": {"$sum": 1},
                "total_late_minutes": {"$sum": "$late_minutes"},
            }
        },
        {
            "$setWindowFields": {
                "sortBy": {
                    "late_count": -1,
                    "total_late_minutes": -1,
                },
                "output": {
                    "rank": {"$rank": {}},
                },
            }
        },
        {
            "$sort": {
                "rank": 1,
                "_id": 1,
            }
        },
        {"$limit": limit},
        {
            "$project": {
                "_id": 0,
                "emp_code": "$_id",
                "late_count": 1,
                "total_late_minutes": 1,
                "rank": 1,
            }
        },
    ]

    rows = list(attendance.aggregate(pipeline))

    return {
        "month": month,
        "limit": limit,
        "leaderboard": rows,
    }


# ---------------------------------------------------------
# Department daily trend
# ---------------------------------------------------------



@app.get("/analytics/departments/{department}/trend")
def department_trend(
    department: str,
    start_date: str,
    end_date: str,
) -> dict:
    first_day = parse_calendar_date(start_date)
    last_day = parse_calendar_date(end_date)

    if first_day > last_day:
        raise HTTPException(
            status_code=422,
            detail="start_date must be on or before end_date.",
        )

    employees_in_department = employees.find(
        {
            "department": department,
            "joined_on": {"$lte": last_day.isoformat()},
        },
        {"_id": 0, "emp_code": 1},
    )

    employee_codes = [
        item["emp_code"] for item in employees_in_department
    ]

    pipeline = [
        {
            "$match": {
                "emp_code": {"$in": employee_codes},
                "date": {
                    "$gte": first_day.isoformat(),
                    "$lte": last_day.isoformat(),
                },
            }
        },
        {
            "$addFields": {
                "_weekday": {
                    "$dayOfWeek": {
                        "$dateFromString": {
                            "dateString": "$date",
                            "format": "%Y-%m-%d",
                        }
                    }
                }
            }
        },
        {
            "$group": {
                "_id": "$date",
                "present_days": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    {
                                        "$in": [
                                            "$status",
                                            ["PRESENT", "WFH", "ON_DUTY"],
                                        ]
                                    },
                                    {
                                        "$in": [
                                            "$_weekday",
                                            [2, 3, 4, 5, 6],
                                        ]
                                    },
                                ]
                            },
                            {
                                "$cond": [
                                    "$half_day",
                                    0.5,
                                    1.0,
                                ]
                            },
                            0,
                        ]
                    }
                },
                "late_count": {
                    "$sum": {
                        "$cond": [
                            {"$gt": ["$late_minutes", 0]},
                            1,
                            0,
                        ]
                    }
                },
                "total_overtime_minutes": {
                    "$sum": {
                        "$ifNull": ["$overtime_minutes", 0]
                    }
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "date": {
                    "$dateFromString": {
                        "dateString": "$_id",
                        "format": "%Y-%m-%d",
                    }
                },
                "present_days": 1,
                "late_count": 1,
                "total_overtime_minutes": 1,
            }
        },
        {"$sort": {"date": 1}},
        {
            "$densify": {
                "field": "date",
                "range": {
                    "step": 1,
                    "unit": "day",
                    "bounds": [
                        datetime.combine(
                            first_day, datetime.min.time()
                        ),
                        datetime.combine(
                            last_day + timedelta(days=1),
                            datetime.min.time(),
                        ),
                    ],
                },
            }
        },
        {
            "$fill": {
                "output": {
                    "present_days": {"value": 0},
                    "late_count": {"value": 0},
                    "total_overtime_minutes": {"value": 0},
                }
            }
        },
        {
            "$setWindowFields": {
                "sortBy": {"date": 1},
                "output": {
                    "avg_present_days_7d": {
                        "$avg": "$present_days",
                        "window": {"documents": [-6, 0]},
                    }
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "date": {
                    "$dateToString": {
                        "format": "%Y-%m-%d",
                        "date": "$date",
                        "timezone": "UTC",
                    }
                },
                "present_days": {
                    "$round": ["$present_days", 2]
                },
                "late_count": 1,
                "total_overtime_minutes": 1,
                "avg_present_days_7d": {
                    "$round": ["$avg_present_days_7d", 2]
                },
            }
        },
        {"$sort": {"date": 1}},
    ]

    rows = list(attendance.aggregate(pipeline))

    return {
        "department": department,
        "start_date": start_date,
        "end_date": end_date,
        "trend": rows,
    }


# ---------------------------------------------------------
# Query-plan inspection
# ---------------------------------------------------------

@app.get("/admin/explain/{endpoint}")
def explain_endpoint(
    endpoint: str = Path(
        description="attendance_list, employee_monthly, department_summary, "
                    "late_leaderboard, or department_trend"
    ),
) -> dict:
    allowed = {
        "attendance_list",
        "employee_monthly",
        "department_summary",
        "late_leaderboard",
        "department_trend",
    }

    if endpoint not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"endpoint must be one of: {', '.join(sorted(allowed))}",
        )

    try:
        if endpoint == "attendance_list":
            plan = attendance.find({}).sort(
                [("date", DESCENDING), ("emp_code", ASCENDING)]
            ).explain()

        elif endpoint == "employee_monthly":
            plan = attendance.aggregate(
                [
                    {
                        "$match": {
                            "emp_code": "EMP0001",
                            "date": {
                                "$gte": "2026-01-01",
                                "$lte": "2026-01-31",
                            },
                        }
                    }
                ],
                explain=True,
            )

        elif endpoint == "department_summary":
            plan = employees.find(
                {"joined_on": {"$lte": "2026-01-31"}}
            ).explain()

        elif endpoint == "late_leaderboard":
            plan = attendance.find(
                {
                    "date": {
                        "$gte": "2026-01-01",
                        "$lte": "2026-01-31",
                    },
                    "late_minutes": {"$gt": 0},
                }
            ).explain()

        else:
            plan = attendance.find(
                {
                    "date": {
                        "$gte": "2026-01-01",
                        "$lte": "2026-01-31",
                    }
                }
            ).explain()

        return {
            "endpoint": endpoint,
            "explain": plan,
        }

    except PyMongoError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Unable to obtain query plan: {str(exc)}",
        )


# --------------------------------------------------------------------------- #
# TODO - the rest of the contract (see openapi.yaml):
#   POST  /attendance/punch-out
#   PATCH /attendance/{emp_code}/{date}
#   GET   /analytics/employees/{emp_code}/monthly
#   GET   /analytics/departments/summary
#   GET   /analytics/leaderboard/late
#   GET   /analytics/departments/{department}/trend
#   GET   /admin/explain/{endpoint}
# --------------------------------------------------------------------------- #
