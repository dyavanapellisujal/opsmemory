# Incident 09: RabbitMQ Connection Exhaustion
**Severity:** SEV-3
**Date:** 2026-06-05
**Affected Services:** email-sender, rabbitmq

## Description
No welcome emails were being sent. RabbitMQ rejected new connections.

## Root Cause
The `email-sender` service opened a new TCP connection to RabbitMQ for every single email sent instead of reusing a connection pool, exhausting the file descriptors on the broker.

## Resolution
Restarted the `email-sender` pods and applied a patch to use connection pooling.
```bash
rabbitmqctl close_all_connections "Emergency reset"
kubectl rollout restart deployment/email-sender
```

## Lessons Learned
Never open connections per request. Use AMQP connection pooling and multiplex channels over a single TCP connection.
