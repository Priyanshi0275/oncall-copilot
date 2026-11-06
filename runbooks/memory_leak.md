# Runbook: Memory leak

## Symptoms
- Memory usage climbs steadily and never drops
- Container restarts with OOMKilled
- Latency grows over time before the crash

## Diagnosis
1. Check memory metrics over the last several hours.
2. Check whether the climb started after a deploy.

## Fix
- Restart the service to restore capacity (temporary).
- If it started after a deploy, roll back.

## Risk
Restart causes brief disruption. Needs human approval.