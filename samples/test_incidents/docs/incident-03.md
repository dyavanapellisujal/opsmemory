# Incident 03: API Gateway TLS Expiry
**Severity:** SEV-1
**Date:** 2026-07-01
**Affected Services:** api-gateway, frontend

## Description
Total outage for external customers. The browser showed SSL certificate errors, and all API requests failed with `ERR_CERT_DATE_INVALID`.

## Root Cause
The TLS certificate for `api.example.com` expired. The cert-manager pod had crashed three days prior, so the automated Let's Encrypt renewal never happened.

## Resolution
Deleted the stuck cert-manager pod so it would restart and successfully complete the ACME challenge.
```bash
kubectl delete pod -n cert-manager -l app=cert-manager
# Force renewal
cmctl renew api-gateway-cert -n ingress-nginx
```

## Lessons Learned
We cannot rely solely on cert-manager without monitoring it. We need external blackbox monitoring for SSL certificate expiry (e.g., alert at 14 days remaining).
