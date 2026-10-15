# Employee Attendance & Analytics API

A RESTful backend for employee management, attendance tracking, attendance correction, and workforce analytics, built with **FastAPI, Python, and MongoDB**.

## Tech Stack

- Python 3.11+
- FastAPI
- MongoDB
- PyMongo
- Pydantic
- Uvicorn
- OpenAPI / Swagger UI

## Features

- Employee creation and listing with filtering and pagination
- Attendance punch-in and punch-out workflows
- Shift-based attendance calculations, including overnight shifts
- Late-arrival, overtime, and half-day calculations
- Attendance correction with audit history
- Attendance filtering by employee, department, status, and date range
- Monthly employee attendance analytics
- Department-level attendance summaries
- Late-arrival leaderboard with ranking
- Department attendance trends with seven-day rolling averages
- MongoDB index creation during application startup
- Health endpoint for application and database availability
- Query-plan inspection endpoint for attendance and analytics queries

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Check application and database health |
| POST | `/employees` | Create an employee |
| GET | `/employees` | List employees |
| POST | `/attendance/punch-in` | Record employee punch-in |
| POST | `/attendance/punch-out` | Record employee punch-out |
| GET | `/attendance` | List and filter attendance records |
| PATCH | `/attendance/{emp_code}/{date}` | Correct an attendance record |
| GET | `/analytics/employees/{emp_code}/monthly` | Employee monthly analytics |
| GET | `/analytics/departments/summary` | Department-level summary |
| GET | `/analytics/leaderboard/late` | Late-arrival leaderboard |
| GET | `/analytics/departments/{department}/trend` | Department attendance trend |
| GET | `/admin/explain/{endpoint}` | Inspect MongoDB query execution plans |

Interactive API documentation is available at `/docs` when the application is running.

## Business Rules

- API timestamps use Unix epoch milliseconds.
- Attendance dates use the `YYYY-MM-DD` format and follow the IST calendar.
- Shift times use the 24-hour `HH:MM` format.
- Overnight shifts are supported.
- Late arrival is counted only when an employee is more than 10 minutes late.
- Overtime is counted when time beyond the shift end reaches at least 30 minutes; only complete minutes are counted.
- Work hours are rounded to two decimal places using half-up rounding.
- A half-day is recorded when rounded work hours are below 4.50.
- Working-day calculations use Monday through Friday.
- Weekend attendance records can still contribute to late-arrival and overtime metrics.

## Prerequisites

- Python 3.11 or newer
- MongoDB
- Git

## Setup

### 1. Clone the Repository

Replace the placeholders with your actual public GitHub repository URL and directory name.

```bash
git clone <YOUR_PUBLIC_GITHUB_REPOSITORY_URL>
cd <YOUR_REPOSITORY_DIRECTORY>
```

### 2. Create a Virtual Environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```powershell
python -m pip install -r requirements.txt
```

### 4. Configure MongoDB

Set the MongoDB connection details in PowerShell:

```powershell
$env:MONGO_URI = "your-mongodb-connection-string"
$env:MONGO_DB = "employee_attendance"
```

Use your own MongoDB connection details and ensure the database is accessible.

**Security:** Never commit database credentials, secrets, or private connection strings.

### 5. Load Sample Data (Optional)

If a seed script is included in the repository, run its actual filename from the project root. For example:

```powershell
python sample_seed.py
```

Skip this step if no seed script is included or sample data is not required.

### 6. Run the Application

Run from the repository root:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Access the API

- **Base URL:** http://127.0.0.1:8000
- **Swagger UI:** http://127.0.0.1:8000/docs
- **Health Check:** http://127.0.0.1:8000/health

The health endpoint reports database availability. A database connectivity failure should return HTTP 503.

## Database Design

The application uses two MongoDB collections:

- **`employees`** — Stores employee identifiers, department, joining date, and shift information.
- **`attendance_logs`** — Stores attendance dates, punch timestamps, attendance status, calculated metrics, and correction history.

Employee records are linked to attendance records through `emp_code`.

API timestamps use Unix epoch milliseconds, while timestamps are stored in MongoDB as BSON datetime values in UTC.

The application creates required indexes during startup. Index usage and query performance should be verified against the assignment's expected query patterns and dataset size.

See `DATA_MODEL.md` for additional data-model details.

## Validation and Testing

The following behaviors have been manually checked during development:

- No-op attendance corrections are rejected.
- Unsupported attendance status values are rejected.
- Invalid punch order is rejected.
- Missing attendance records return HTTP 404.
- Attendance dates before an employee's joining date are rejected.
- Duplicate punch-in requests are rejected.
- Attendance correction history is recorded for valid changes.
- Department summary and trend calculations have been exercised with sample data.
- MongoDB `executionStats` output has been verified for a sample attendance query.

These are manual development checks, not a complete automated test suite. Concurrency behavior, all analytics edge cases, and performance on a 100,000-record dataset require further verification.

## Known Verification Gaps

Before considering the assignment fully verified, check:

- Query-plan inspection against the actual endpoint filters, pipelines, sorting, and pagination.
- Index usage and execution statistics with a representative large dataset.
- Concurrent punch-in, punch-out, and attendance correction behavior.
- Regression tests covering the assignment's business rules.
- Consistency between the documentation and final implementation.

## Repository Contents

The repository should include the relevant project files:

- `app/main.py` — FastAPI application and endpoint implementation
- `requirements.txt` — Python dependencies
- `README.md` — Project documentation
- `openapi.yaml` — API specification
- `DATA_MODEL.md` — Data model documentation
- `REVIEW.md` — Review of starter-code issues and fixes
- `DECISIONS.md` — Engineering decisions
- Sample data and seed scripts, if included

Do not commit `.venv`, Python cache files, `.env` files containing secrets, credentials, or database dumps.
