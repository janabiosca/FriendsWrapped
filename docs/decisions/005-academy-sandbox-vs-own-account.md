# 005 · AWS Academy for dev, own account for prod

**Context.** The project currently runs in an AWS Academy sandbox. A regular AWS account is an optional future deployment. In Academy,
IAM roles cannot be created (everything runs as `LabRole`), credentials expire with each lab
session, and the sandbox is not meant to run unattended for weeks. Spotify returns up to 50 plays per request; available pagination does not guarantee
unlimited recovery after interruptions.

**Decision.** One deployed environment and one prepared configuration using the ingestion module:
- `dev` (Academy): `LabRole`, AWS managed encryption, destroyable. Hosts the current real listening history and the MVP.
- `prod` (own account): one least-privilege role per function, deletion protection, customer
  managed KMS key, intended for continuous operation when deployed. It has not been deployed. GitHub Actions can use
  OIDC (`infra/bootstrap/github-oidc`): no AWS keys stored in GitHub when those roles are configured. The OIDC roles are not deployed.

**Alternatives.** Everything in Academy (free, but gaps in the data and no least privilege),
or everything in the own account (no safe place to experiment).

**Consequences.** Own-account costs have not been measured. Connection, dashboard and
Wrapped currently have Academy-specific stacks; prod covers ingestion only. The module has two variables (`lab_role_name`,
`customer_managed_key`) that switch between both worlds, covered by `terraform test`.

## Academy S3 read restriction

The lab service control policy explicitly denies GetBucketObjectLockConfiguration.
The AWS provider reads it while managing aws_s3_bucket, so dev reuses the existing
bucket via existing_raw_bucket. Its encryption, public access block, TLS policy,
versioning and lifecycle are still managed by Terraform. The bucket itself must
be bootstrapped separately (as with the state bucket) and is retained on destroy.
Prod continues to manage its bucket normally. This does not change lab permissions.
