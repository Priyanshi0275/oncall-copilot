# Runbook: Errors started right after a deploy

## Symptoms
- Error rate rises immediately after a "deployed new version" event
- Errors were not present in the previous version

## Diagnosis
1. Compare the timestamp of the latest deploy with the first error.
2. If errors start within a few minutes of the deploy, suspect the new version.

## Fix
Roll back to the previous known-good version. Do this first, investigate after.

## Risk
Low. Rollback restores the last version that was working.