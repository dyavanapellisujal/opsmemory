# Incident 02: Kubernetes Node OOM Evictions
**Severity:** SEV-3
**Date:** 2026-07-03
**Affected Services:** image-resizer, worker-nodes

## Description
Multiple pods of the `image-resizer` service were evicted continuously, and some worker nodes went into `NotReady` state due to memory pressure.

## Root Cause
A memory leak in the image processing library caused the pods to consume memory beyond their limits. Because the `limits.memory` was not set, the pods consumed all node memory, causing the kubelet to crash under memory pressure.

## Resolution
Cordoned the affected nodes, drained them, and deployed a hotfix to `image-resizer` that added strict memory limits and a restart policy.
```bash
# Cordon and drain
kubectl cordon node-xyz
kubectl drain node-xyz --ignore-daemonsets --delete-emptydir-data

# Update resources
kubectl set resources deployment image-resizer -c resizer --limits=memory=2Gi
```

## Lessons Learned
All pods must have strict memory limits defined in their manifests to prevent noisy neighbors from crashing the node.
