# payments-api

The payments-api service processes all customer payment transactions.

## Overview

payments-api depends on redis for session caching and payments-api depends on postgres
for transactional storage. Events are published to kafka for downstream consumers.

- **Owner**: Platform Engineering
- **Environment**: production
- **Namespace**: payments
- **Runtime**: Kubernetes

## Deployment

Deployments are performed with Helm:

```bash
helm upgrade --install payments-api charts/payments-api -n payments
```

Always validate the ConfigMap before rollout — most historical deployment
failures were caused by invalid environment variables in the ConfigMap.

## Configuration

| Variable | Purpose |
|----------|---------|
| REDIS_HOST | Redis endpoint for session cache |
| DATABASE_URL | PostgreSQL connection string |
| KAFKA_BROKERS | Kafka bootstrap servers |
