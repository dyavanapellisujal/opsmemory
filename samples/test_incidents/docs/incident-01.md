# Incident 01: orders-db Postgres Deadlocks
**Severity:** SEV-2
**Date:** 2026-07-04
**Affected Services:** orders-db, payment-processor

## Description
At 09:00 UTC, the `orders-db` Postgres cluster began experiencing high lock contention leading to deadlocks. The `payment-processor` service was unable to commit transactions, causing a spike in 500 errors for checkout flows.

## Root Cause
A recent deployment introduced a new background job in `payment-processor` that updated order statuses across multiple tables in a different order than the main checkout flow. This caused classic AB/BA deadlocks in Postgres.

## Resolution
Killed the blocking queries and rolled back the background job deployment to restore service.
```bash
# Find blocking queries
SELECT pid, query FROM pg_stat_activity WHERE wait_event_type = 'Lock';
# Kill them
SELECT pg_terminate_backend(<pid>);
# Rollback deployment
kubectl rollout undo deployment/payment-processor -n production
```

## Lessons Learned
Database transactions updating multiple tables must always acquire row locks in the same consistent order across all services.
