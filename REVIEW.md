# Code Review — Employee Attendance & Analytics API

## 1. Identified Defects and Fixes

The following table documents the issues identified during development, how they can be detected, and the corresponding fixes.

| # | Function / Area | Defect | Detection Method | Fix Applied |
|---|---|---|---|---|
| 1 | `correct_attendance()` | The `changes` dictionary was accessed before initialization, potentially causing an `UnboundLocalError`. | Submit a valid attendance correction and inspect the application response and logs. | Initialize `changes` before comparing the requested values with the existing record. |
| 2 | `correct_attendance()` | A correction request containing no effective changes could create a misleading correction operation. | Submit the same values already stored in the attendance record and inspect the response and audit history. | Reject no-op corrections with HTTP 422 and avoid creating an audit entry. |
| 3 | Attendance status validation | Unsupported attendance status values could be accepted if they were not explicitly validated. | Submit a status outside the supported set, such as `HOLIDAY_INVALID`. | Validate the requested status and return HTTP 422 for unsupported values. |
| 4 | Punch-out validation | A punch-out timestamp earlier than the punch-in timestamp would produce an invalid attendance interval. | Submit a punch-out timestamp earlier than the recorded punch-in timestamp. | Validate timestamp ordering and reject invalid requests with HTTP 422. |
| 5 | Attendance date validation | Attendance could be recorded for a date before the employee's joining date. | Attempt to create attendance for a date earlier than the employee's joining date. | Validate the attendance date against the employee's joining date and reject invalid requests. |
| 6 | Punch-in uniqueness | Duplicate attendance records could be created for the same employee and date without database-level uniqueness enforcement. | Submit repeated punch-in requests for the same employee and date, including concurrent requests. | Enforce a unique compound index on employee code and attendance date, and handle duplicate-key errors with HTTP 409. |

## 2. Additional Areas Reviewed

- **Employee uniqueness:** A unique index on employee code enforces database-level uniqueness.
- **Daily attendance uniqueness:** A unique compound index prevents multiple attendance records for the same employee and date.
- **Department summaries:** The aggregation preserves employees without attendance records, preventing them from disappearing from department headcount calculations.
- **Leaderboard ordering:** Employee code provides a deterministic tie-breaker when employees have the same ranking metrics.
- **Query-plan interpretation:** A collection scan on a small sample dataset alone is insufficient evidence that an index is missing or ineffective.

## 3. Remaining Verification Work

This review records the defects identified so far and is not an exhaustive audit of the original starter implementation.

The following areas require further verification against the assignment requirements:

- Strict validation of timestamp types and epoch-millisecond values.
- Shift-boundary, overnight-shift, late-arrival, and overtime calculations.
- Half-day and work-hours rounding rules.
- Concurrent punch-out and attendance-correction behavior.
- Audit-history consistency under concurrent corrections.
- Monthly analytics, department summaries, leaderboard ranking, and trend calculations.
- Query-plan behavior using the actual endpoint filters and aggregation pipelines.
- Index usage and execution statistics on a representative large dataset.

Only defects confirmed against the original starter code should be added to the identified-defects table. Each additional entry should include a reproducible test or symptom and the corresponding verified fix.
