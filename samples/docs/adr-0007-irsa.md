# ADR-0007: Adopt IRSA for workload AWS access

Status: Accepted

## Context

Services previously used long-lived AWS access keys stored in Kubernetes
Secrets. Keys leaked twice and rotation was manual.

## Decision

Adopt IAM Roles for Service Accounts (IRSA). Every workload assumes a
dedicated IAM role through its Kubernetes service account; no static AWS
credentials exist in the cluster.

## Consequences

- No more static AWS keys in Secrets.
- Terraform module `terraform-irsa` provisions per-service roles.
- payments-api and orders-api migrated first; all production services use IRSA.
