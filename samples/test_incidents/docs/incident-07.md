# Incident 07: Kafka Consumer Lag
**Severity:** SEV-3
**Date:** 2026-06-15
**Affected Services:** analytics-pipeline, kafka

## Description
Analytics dashboards were delayed by over 4 hours. 

## Root Cause
A poison pill message with a malformed JSON payload caused the `analytics-pipeline` consumer to throw an exception, fail to commit the offset, and continuously retry the same message indefinitely.

## Resolution
Manually skipped the offset for the consumer group using the Kafka CLI.
```bash
kafka-consumer-groups.sh --bootstrap-server broker:9092 --group analytics-group --topic events --reset-offsets --shift-by 1 --execute
```

## Lessons Learned
Consumers must implement Dead Letter Queues (DLQ) to catch and quarantine unparseable messages instead of retrying them forever.
