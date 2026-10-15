# Employee Attendance & Analytics API

A FastAPI and MongoDB backend for employee management, attendance tracking, manual attendance corrections, and department-level analytics.

## Technology Stack

- Python and FastAPI
- MongoDB with PyMongo
- Uvicorn
- REST APIs documented through OpenAPI/Swagger

## Features

- Employee and attendance management
- Punch-in and attendance correction validation
- Attendance calculations based on employee shifts
- Audit history for manual corrections
- Attendance listing and analytics endpoints
- MongoDB query explain endpoints for performance inspection

## Prerequisites

- Python 3.10 or compatible with the installed dependencies
- MongoDB 6.0 or newer
- Git

## Setup

Create and activate a virtual environment on Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Configure the MongoDB connection using the environment variables `MONGO_URI` and `MONGO_DB`, as supported by the application.

Load the supplied sample data if required:

```powershell
python sample_seed.py
```

Start the API:

```powershell
python -m uvicorn app.main:app --port 8000
```

Open Swagger UI at http://127.0.0.1:8000/docs.

## Database

The application uses the `employees` and `attendance_logs` collections. Attendance dates represent IST calendar days; punch timestamps are exchanged through the API as epoch milliseconds.

## Validation and Testing

The attendance correction endpoint has been manually checked for no-op corrections, invalid status values, invalid punch order, missing attendance records, and dates before an employee's joining date.

A successful Python syntax check was also performed on `app/main.py`. These checks do not replace the full automated test suite or verification against the assignment's large dataset.

## Known Limitations

Full verification against the grader's larger dataset, including all analytics edge cases and index execution plans, must be completed before claiming complete assignment compliance.