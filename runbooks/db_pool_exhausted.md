# Runbook: Database connection pool exhausted

## Symptoms
- Log line: "database connection pool exhausted"
- HTTP 500 errors on endpoints that touch the database

## Diagnosis
1. Check whether the errors began after a deploy (leaked connections in new code).
2. Check whether traffic spiked.

## Fix
- If it began after a deploy: roll back to the previous version.
- If it began with a traffic spike and no deploy: scale up replicas and review pool size.

## Risk
Rollback is low risk. Changing pool size requires a human decision.