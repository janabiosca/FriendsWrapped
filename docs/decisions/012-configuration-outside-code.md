# 012 · Account-specific configuration outside the code

**Context.** The first deployment hard-coded values that only exist in one AWS account or
group: the raw bucket name, the Athena listener IDs, the administrator's name in user-facing
messages and the member lists in administration scripts. Deploying from another account or
workstation failed, or silently produced empty Athena results.

**Decision.** Every account- or group-specific value is a Terraform variable or a script
argument:

| Value | Where it is set |
|---|---|
| Raw bucket (`existing_raw_bucket`) | `terraform.tfvars` or `RAW_BUCKET_NAME` |
| Listener IDs (`listener_ids`) | `TF_VAR_listener_ids` or `LISTENER_IDS` |
| Administrator name (`admin_name` → `ADMIN_NAME`) | `ADMIN_NAME`, default "la administradora del grupo" |
| Collection schedule (`collect_schedule`) | `COLLECT_SCHEDULE` |
| Notice recipients (`wrapped_notice_emails`) | `WRAPPED_NOTICE_EMAILS` secret |
| Member checks in scripts | read from the group membership in DynamoDB, plus `--table`, `--connect-table`, `--group`, `--user-id` |

Required values have no default, so a missing value stops the plan instead of deploying
something wrong. Personal values (`terraform.tfvars`, `backend.conf`) are git-ignored.

**Alternatives.** Separate copies of the code per account (drift between copies); SSM
Parameter Store lookups (one more service and permission for a handful of values).

**Consequences.** The same commit deploys to any account by changing configuration only;
this was exercised on 22 November 2026 from a second workstation with 0 resources destroyed.
Every deployment must supply the same values as the previous one, or the plan shows the
difference: reviewing the plan before applying is essential.
