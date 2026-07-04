# Incident 05: Search API Missing Elasticsearch Index
**Severity:** SEV-2
**Date:** 2026-06-25
**Affected Services:** search-api, elasticsearch

## Description
Search functionality returned empty results for all users. The `search-api` logged `index_not_found_exception`.

## Root Cause
An automated cleanup script aggressively deleted indices older than 30 days, but accidentally matched the active product alias due to a missing wildcard boundary.

## Resolution
Restored the index from the nightly AWS Elasticsearch snapshot and fixed the cleanup script.
```bash
# Restore from snapshot
curl -X POST "es-cluster/_snapshot/nightly/snap_1/_restore" -H 'Content-Type: application/json' -d'
{
  "indices": "products-v1"
}'
```

## Lessons Learned
Destructive cleanup scripts must operate on specific date patterns, not generic substring matches. Add a "dry-run" mode to all cron jobs that delete data.
