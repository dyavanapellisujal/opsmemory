# Incident 06: Redis Cache Stampede
**Severity:** SEV-2
**Date:** 2026-06-20
**Affected Services:** catalog-service, redis

## Description
The `catalog-service` database CPU spiked to 100%, causing a cascading failure across the frontend.

## Root Cause
The cached homepage product catalog expired. Thousands of concurrent requests hit the cache, missed, and all simultaneously queried the Postgres database (a cache stampede/thundering herd).

## Resolution
Implemented a distributed lock (redlock) around the cache miss query. Restarted the database to clear connections.
```bash
# Restart pg pooler
systemctl restart pgbouncer
```

## Lessons Learned
Expensive database queries triggered on cache misses must be protected by a distributed lock or use a probabilistic early expiration strategy.
