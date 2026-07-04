# Incident #42 Postmortem: Redis authentication outage

**Severity**: SEV2 · **Duration**: 47 minutes · **Services affected**: payments-api

## Summary

payments-api entered CrashLoopBackOff because redis authentication failed.
The password stored in the `redis-credentials` Kubernetes Secret had expired.

## Timeline

- 14:02 — Alerts fired: payments-api 5xx rate above threshold
- 14:10 — Pods observed in CrashLoopBackOff with `AUTH failed` log entries
- 14:31 — Root cause identified: expired redis credentials
- 14:41 — Credentials rotated, deployment restarted
- 14:49 — Service fully recovered

## Root cause

The redis password expired after 90 days and no alert existed for Secret age.

## Resolution

Rotated the Kubernetes Secret and restarted the payments-api Deployment.

## Lessons learned

Rotate credentials before expiration and alert on Secret age 14 days ahead.
