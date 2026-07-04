# Incident 08: DNS Resolution Failure
**Severity:** SEV-2
**Date:** 2026-06-10
**Affected Services:** payment-gateway, core-dns

## Description
Outgoing payments failed with `NXDOMAIN` when trying to resolve the Stripe API.

## Root Cause
CoreDNS pods in the Kubernetes cluster were scaled down to 1 during a node rotation and became overwhelmed by UDP traffic, dropping DNS queries.

## Resolution
Scaled up CoreDNS and added a Horizontal Pod Autoscaler based on QPS.
```bash
kubectl scale deployment coredns -n kube-system --replicas=3
```

## Lessons Learned
CoreDNS must have a minimum of 3 replicas and NodeLocal DNS cache should be enabled to prevent cluster-wide DNS bottlenecks.
