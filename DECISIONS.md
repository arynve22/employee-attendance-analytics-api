\# DECISIONS.md



1\. \*\*Indexes.\*\* I created six indexes. A unique index on `employees.emp\_code` prevents duplicate employee codes. A unique compound index on `attendance\_logs.emp\_code` and `date` guarantees at most one attendance record per employee per day. The department and joining-date index supports employee filtering, while the date/employee and status/date/employee indexes support attendance queries. The punch-in timestamp index supports punch-in lookups. I did not add a separate email index because employee-code uniqueness is the primary identity guarantee in this assignment.



2\. \*\*Punch-in race.\*\* If two identical punch-ins arrive together, both may attempt an insert. The unique employee/date index allows only one insert to succeed. The other raises `DuplicateKeyError`, which the API handles as HTTP 409. This depends on the unique index being created successfully.



3\. \*\*Ties.\*\* Employees with equal leaderboard ranking values share a rank. Employee code provides deterministic ordering, and the requested limit is applied after ranking. The exact cutoff behavior should be confirmed with a tie-at-limit test.



4\. \*\*Headcount.\*\* The department summary starts from employees and uses `$lookup` with `preserveNullAndEmptyArrays: true`, so employees without attendance logs are retained and counted.



5\. \*\*Scaling.\*\* For 100 times the data, I would test realistic workloads, inspect execution plans, measure latency, and tune indexes and aggregation pipelines using those results.
