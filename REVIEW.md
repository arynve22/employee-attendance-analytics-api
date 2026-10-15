# REVIEW.md

## Defects and fixes

| # | Where (function / area) | What is wrong | How you'd notice it (test, input, or symptom) | How you fixed it |
|---|---|---|---|---|
| 1 | `correct_attendance()` | `changes` was used before initialization. | Submit an attendance correction and check for `UnboundLocalError`. | Initialize `changes` as an empty dictionary before comparing fields. |
| 2 | `correct_attendance()` | A correction with no actual changes should not create a misleading correction. | Submit the current values again and inspect the response and audit history. | Return HTTP 422 when no changes are detected. |
| 3 | Attendance correction validation | Unsupported attendance statuses must be rejected. | Submit an invalid status such as `HOLIDAY_INVALID`. | Validate the status and return HTTP 422 for unsupported values. |
| 4 | Punch-out validation | Punch-out must not precede punch-in. | Submit a punch-out timestamp earlier than punch-in. | Validate the time order and return HTTP 422 for invalid input. |
| 5 | Attendance date validation | Attendance must not precede an employee's joining date. | Submit an attendance date before the employee's joining date. | Reject the request with HTTP 422. |
| 6 | Punch-in uniqueness | Duplicate attendance records for the same employee and date must be prevented, including concurrent requests. | Send duplicate punch-in requests for the same employee and date. | Use a unique compound index and return HTTP 409 when a duplicate insert is detected. |

## Reviewed areas

- The unique employee-code index enforces employee-code uniqueness.
- The unique employee/date attendance index prevents duplicate daily attendance records.
- Department summaries preserve employees with no attendance records using `$lookup` and `preserveNullAndEmptyArrays`.
- Leaderboard output uses employee code as a deterministic tie-breaker.
- A collection scan on a tiny sample alone does not prove that an index is defective or unnecessary.

## Remaining review work

This is a partial list of identified issues, not a claim that every defect in the original starter has been found. Additional helper functions and endpoints, concurrency cases, analytics edge cases, and query plans must be checked before the review can be considered complete.