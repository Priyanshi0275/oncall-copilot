# Runbook: High latency

## Symptoms
- Response times well above normal
- No spike in errors, only slowness

## Diagnosis
1. Check request volume for a traffic spike.
2. Check whether a slow downstream dependency is involved.

## Fix
- Traffic spike: scale up replicas.
- Slow dependency: escalate to the owning team, do not restart blindly.

## Risk
Scaling is low risk. Escalation is a human action.