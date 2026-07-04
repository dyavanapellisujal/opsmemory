# Incident 04: S3 Permission Denied on Image Uploads
**Severity:** SEV-3
**Date:** 2026-06-28
**Affected Services:** user-profile-service, aws-s3

## Description
Users were unable to upload profile pictures. The service logged `AccessDenied` errors when trying to call `PutObject` on the S3 bucket.

## Root Cause
An infrastructure-as-code (Terraform) change accidentally removed the `s3:PutObject` permission from the IAM role assumed by the `user-profile-service`.

## Resolution
Reverted the Terraform PR and re-applied the state.
```bash
# Check assumed role
aws sts get-caller-identity
# Re-apply terraform
terraform apply -target=aws_iam_role.profile_service_role
```

## Lessons Learned
IAM policy changes need stricter review. We should implement IAM Access Analyzer in the CI pipeline to catch missing permissions before they are deployed.
