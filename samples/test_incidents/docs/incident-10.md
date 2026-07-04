# Incident 10: SQS DLQ Filling Up
**Severity:** SEV-4
**Date:** 2026-06-01
**Affected Services:** invoice-service, aws-sqs

## Description
The Dead Letter Queue for invoices triggered an alarm for > 10,000 messages.

## Root Cause
An upstream system changed the date format in the event payload from ISO8601 to a Unix timestamp. The `invoice-service` failed to parse it and sent all messages to the DLQ.

## Resolution
Updated the parsing logic in `invoice-service` to support both formats and drove a redrive of the DLQ.
```bash
aws sqs start-message-move-task --source-arn arn:aws:sqs:us-east-1:123:invoice-dlq --destination-arn arn:aws:sqs:us-east-1:123:invoice-queue
```

## Lessons Learned
API contracts via message queues must be versioned. Schema validation should occur at the producer level before publishing.
