# Runbook: Redis Recovery

This runbook covers recovery procedures for redis outages affecting payments-api.

## Symptoms

- payments-api pods in CrashLoopBackOff
- `AUTH failed` errors in application logs
- Elevated 5xx rates on the payments API

## Diagnosis

1. Check redis pod status: `kubectl get pods -n payments -l app=redis`
2. Check credential age: redis passwords are stored in the `redis-credentials`
   Kubernetes Secret and expire every 90 days.
3. Check connectivity from a debug pod.

## Recovery

1. Rotate the credentials in the `redis-credentials` Secret.
2. Restart the payments-api Deployment:
   `kubectl rollout restart deployment/payments-api -n payments`
3. Verify pods become Ready and error rates drop.

## Lessons

Rotate credentials before expiration. Alert 14 days before Secret expiry.
