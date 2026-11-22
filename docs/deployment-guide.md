# Deployment and technical reference

Run the commands below from the repository root. This guide contains deployment details, configuration and implementation limits.

Listening statistics and a weekly Wrapped for a group of friends, built serverless on AWS.

Spotify returns at most **50 plays per request** and does not guarantee unlimited historical access. The first
version (v0.2, *ingestion*) collects connected friends' plays every five minutes while the collection services are running, even when nobody has the
app open, with conditional writes to avoid duplicates and warnings about possible gaps. Everything else (stats, web app, Wrapped, concerts)
is built on top of this history.

The current AWS Academy deployment collects three Spotify accounts every five minutes.
The hosted dashboard supports separate user accounts, shared group profiles, observer
access and weekly PDF downloads. Live concert discovery remains pending provider approval. Personalized SES delivery is
excluded from this delivery. Availability notices use a dedicated Wrapped SNS topic. The `prod` environment is prepared configuration for an optional own account.

## Architecture (v0.2)

```
EventBridge (every 5 minutes) ─► dispatcher λ ─► SQS FIFO (1 message group per user) ─► collector λ ─► DynamoDB (plays, profiles)
                                              │ 3 failures                         │   ├─► S3 raw zone (Hive partitions)
                                              ▼                                    │   └─► Secrets Manager (refresh tokens)
                                        Dead-letter queue ─► CloudWatch alarm ─► SNS ─► email
                                                                  ▲
                         log metric filters (reauth required, possible gap, heartbeat)
```

| Service | Role | Why this one |
|---|---|---|
| EventBridge | Five-minute schedule | Serverless cron, nothing to keep running |
| Lambda (dispatcher, collector) | Fan-out and collection | Short executions on a five-minute schedule: pay per use |
| SQS FIFO + DLQ | One task per user, retries, isolation | A failure only retries that user; FIFO groups stop two concurrent refreshes of the same token |
| DynamoDB (on-demand, PITR) | Plays, profiles, group membership | Key-value access by user and time; conditional writes make collection idempotent |
| S3 (raw zone) | Raw Spotify responses | Cheap durable data lake for Glue/Athena later; rebuild stats if the schema changes |
| Secrets Manager | Spotify refresh tokens | Encrypted, audited, rotated tokens stay out of code and out of Terraform state |
| KMS (prod) | Customer managed key for S3 and SNS | Key policy decides who decrypts; yearly rotation; CloudTrail audit |
| CloudWatch + SNS | Alarms by email | We learn about failures before plays are lost |
| X-Ray | Tracing | One collection end to end: Spotify, Secrets Manager, DynamoDB, S3 |

Design decisions with their alternatives are in [docs/decisions](decisions).

## Repository layout

```
infra/
  modules/ingestion/      reusable module (+ tests/ with a mocked AWS provider)
  envs/dev/               AWS Academy sandbox (LabRole, destroyable)
  envs/prod/              optional own-account configuration (least-privilege roles, KMS)
  connect/                remote Spotify authorization by invitation
  dashboard/              Cognito sign-in and private group statistics
  wrapped/                weekly Step Functions workflow and PDF generation
  analytics/              Glue catalog and bounded Athena SQL analysis
  concerts/               daily concert discovery (disabled pending provider approval)
  bootstrap/github-oidc/  one-off: lets GitHub Actions log in to AWS without stored keys
src/                      Lambda code; the PDF renderer also uses ReportLab
tests/                    pytest + moto (in-memory AWS), Spotify faked
scripts/                  bootstrap_state.sh, connect_spotify.py
.github/workflows/        ci.yml (every push/PR), release.yml (deploy on release)
```

## Environments

| | `dev` | `prod` (optional configuration) |
|---|---|---|
| Account | AWS Academy sandbox | an independently provisioned AWS account |
| IAM | every function runs as `LabRole` (roles cannot be created) | one least-privilege role per function |
| Data | destroyable (`protect_data = false`) | DynamoDB deletion protection, S3 kept |
| Encryption | AWS managed keys | customer managed KMS key |
| Always on | not guaranteed: lab sessions expire and the sandbox can be reset | intended when deployed in an own account |

## Deploy

Requirements: Terraform >= 1.10, AWS CLI, Python 3.12+, credentials of the target account.

1. **Spotify app** (once): create it at developer.spotify.com/dashboard, add
   `http://127.0.0.1:8888/callback` as redirect URI and the three Spotify listeners as users (observers do not need Spotify authorization).
2. **State bucket** (once per account; the only resource outside Terraform):
   ```bash
   scripts/bootstrap_state.sh prod      # writes infra/envs/prod/backend.conf
   ```
3. **Settings**: `cp infra/envs/prod/terraform.tfvars.example infra/envs/prod/terraform.tfvars` and fill it.
4. **Apply**:
   ```bash
   terraform -chdir=infra/envs/prod init -backend-config=backend.conf
   terraform -chdir=infra/envs/prod plan
   terraform -chdir=infra/envs/prod apply
   ```
   Confirm the SNS subscription email AWS sends to `alarm_email`.
5. **Connect each friend** (each one logs in with her own Spotify account):
   ```bash
   python scripts/connect_spotify.py --env prod --client-id <id> --user-id alice --name Alice --email alice@example.com
   ```

Use `dev` the same way in the AWS Academy sandbox (`scripts/bootstrap_state.sh dev`, `infra/envs/dev`).
`terraform destroy` removes a `dev` environment completely; in `prod` it is blocked by deletion protection on purpose.

## CI/CD (GitOps)

GitHub Actions provides CI. AWS deployments have been performed manually; automated
PR plans and release deployment are prepared but require AWS configuration. OIDC roles
have not been deployed. CI success alone does not demonstrate automated deployment.

- **ci.yml**, on every push and pull request: Python tests, `terraform fmt -check`,
  `terraform test` (module tests with mocked AWS), `terraform validate` of each environment,
  Trivy (blocks on HIGH/CRITICAL misconfigurations and on committed secrets) and, on pull
  requests, a `terraform plan` posted as a PR comment.
- **release.yml**, when a GitHub release is published (`v0.2.0`, `v0.3.0`…): tests, then `terraform apply`.
  Give the GitHub environment `prod` required reviewers so production deploys need an approval.

Repository configuration (Settings → Secrets and variables → Actions):

| Name | Type | Value |
|---|---|---|
| `TF_ENV` | variable | `dev` or `prod` |
| `TF_STATE_BUCKET` | variable | bucket printed by `bootstrap_state.sh` (the plan job is skipped until it is set) |
| `AWS_REGION` | variable | `us-east-1` |
| `SPOTIFY_CLIENT_ID` | variable | Spotify app client ID |
| `ALARM_EMAIL` | variable | team email |
| `RAW_BUCKET_NAME` | variable | raw bucket created by hand for `dev` (`aws s3api create-bucket`, see ADR 005) |
| `LISTENER_IDS` | variable | JSON list of Spotify listener IDs for Athena partitions, e.g. `["alice","bob"]` |
| `ADMIN_NAME` | variable | name shown on error pages and the sign-in screen (optional) |
| `COLLECT_SCHEDULE` | variable | collection schedule, e.g. `rate(5 minutes)` (default `rate(1 hour)`) |
| `WRAPPED_NOTICE_EMAILS` | secret | JSON list of weekly notice recipients; must match the current subscribers or the release removes them |
| `AWS_PLAN_ROLE_ARN`, `AWS_APPLY_ROLE_ARN` | variables | own account: outputs of `infra/bootstrap/github-oidc` (short-lived OIDC credentials) |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` | secrets | AWS Academy only (used when the role variables are empty); they expire with the lab session |

To create the OIDC roles in the own account (once, with admin credentials):

```bash
terraform -chdir=infra/bootstrap/github-oidc init -backend-config=../../envs/prod/backend.conf -backend-config="key=bootstrap/github-oidc.tfstate"
terraform -chdir=infra/bootstrap/github-oidc apply -var github_repository=<owner>/<repo> -var state_bucket=<bucket>
```

## Tests

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q                                 # Lambda logic against in-memory AWS
cd infra/modules/ingestion && terraform init && terraform test  # module logic, mocked AWS
```

The tests reproduce the difficulties in the project draft: collecting twice never duplicates,
a crash before the cursor moves never double counts, the same song played twice counts twice,
one friend failing does not affect the others, rotated refresh tokens are saved, rate limits
delay the retry, and a full page of 50 new plays is flagged as a possible gap.

## Demo

- Collect now instead of waiting for the next scheduled run:
  `aws lambda invoke --function-name $(terraform -chdir=infra/envs/dev output -raw dispatcher_function) /dev/stdout`
- The current Academy deployment already uses `rate(5 minutes)`.
- Failure and recovery: a broken token sends that friend's task to the dead-letter queue and
  the alarm emails us; after reconnecting, *SQS → dead-letter queue → Start DLQ redrive*.

## Manual steps (not in Terraform, and why)

| Step | Why it is manual |
|---|---|
| State bucket (`bootstrap_state.sh`) | Terraform needs it before it can run |
| Spotify app and redirect URI | Outside AWS |
| Spotify tokens (`connect_spotify.py`) | Secrets must never go through Terraform state (stored in plain text) |
| Confirm the SNS email | AWS requires the recipient to opt in |
| `infra/bootstrap/github-oidc` | Needs admin rights once; afterwards CI deploys without keys |

## Cost

The deployed environment is AWS Academy, subject to its lab budget and restrictions.
An own-account deployment has not been measured. Costs depend on collection frequency,
active services, retention, region and any applicable credits; do not treat a hypothetical
monthly estimate as a measured project cost.

## Known limitations

- Minutes are estimated from track durations: a skipped song may count as complete.
- History starts when a friend connects. `scripts/import_spotify_history.py` supports importing Spotify history exports when available.
- After the initial seed, collection follows available pages (up to 20 per run), including
  an older-time request when a full page has no next link. The checkpoint only advances
  after all fetched pages are stored. Spotify may still withhold older history; a full
  page after a checkpoint is flagged conservatively as a possible gap.
- A pagination loop, failed request or the 20-page safety limit fails the collection
  without advancing its checkpoint. It is not silently marked complete.
- `dev` is a sandbox: check whether scheduled collections keep running after the AWS Academy
  session ends before relying on it. The current recorded history is stored in `dev`.

## Local dashboard preview

Run `.venv/bin/python scripts/preview_dashboard.py`, then open http://127.0.0.1:8765.
The preview is read-only, bound to loopback on this Mac, and uses the current local
AWS credentials to query the recorded plays of one member (`--user-id`, by default the
first member of the group). It never reads Spotify tokens.
Filters: all recorded history, the last seven calendar days, today, or a selected calendar month (Europe/Madrid).
Refresh reloads stored statistics; collection is independently scheduled in AWS.
The hosted group application is deployed separately through `infra/dashboard`, with
Cognito authentication and group authorization.


## Remote Spotify connection (AWS Academy)

`src/spotify_connect.py` handles invitation-only PKCE authorization over HTTPS.
`infra/connect` is an independent Terraform stack using the existing Academy LabRole,
ingestion table and secret prefix. Its state uses the existing backend bucket with
key `dev/spotify-connect.tfstate`.

```bash
terraform -chdir=infra/connect init -backend-config=../envs/dev/backend.conf -backend-config="key=dev/spotify-connect.tfstate"
terraform -chdir=infra/connect plan -var="spotify_client_id=<app client id>"
terraform -chdir=infra/connect apply -var="spotify_client_id=<app client id>"
terraform -chdir=infra/connect output -raw spotify_redirect_uri
```

Add that exact redirect URI in the Spotify application settings. The owner must
also add each friend in Spotify User Management. Issue invitations locally:

```bash
.venv/bin/python scripts/invite_spotify.py --user-id anna --name Anna --base-url <connect_base_url>
.venv/bin/python scripts/invite_spotify.py --user-id helena --name Helena --base-url <connect_base_url>
```

Send each URL privately to its named recipient. Invitations expire after seven days
and are claimed once. Browser-bound sessions expire after ten minutes. Tokens go
directly to Secrets Manager. An interrupted save may need a replacement invitation;
account binding prevents replacing the member with another Spotify account.
This stack provides onboarding only. It does not expose listening data or provide
the dashboard's sign-in. Its availability depends on the Academy environment.


## Hosted group dashboard (AWS Academy)

`infra/dashboard` deploys the web page, API Gateway JWT authorization, and a Cognito
user pool. The existing `sfw-dev-connect` table stores approved email hashes mapped
to internal member IDs. Public registration is rejected unless the email is approved.
Email verification and active group membership are checked before any statistics are
returned. Profile statistics are restricted to Spotify members of the authenticated user's group.

```bash
terraform -chdir=infra/dashboard init -backend-config=../envs/dev/backend.conf -backend-config="key=dev/dashboard.tfstate"
terraform -chdir=infra/dashboard plan
terraform -chdir=infra/dashboard apply
terraform -chdir=infra/dashboard output -raw dashboard_url
.venv/bin/python scripts/allow_dashboard_member.py --user-id anna --email <approved-email>
```

The user creates her own dashboard password in Cognito and verifies her email.
Spotify authorization remains a separate, invitation-based step. The browser uses
PKCE, keeps the access token in session storage, and requests a fresh login after
expiry. API Gateway checks signature, issuer, audience, expiry and the `openid`
scope; Lambda checks verified email, the approved mapping, and current membership.
The Academy deployment uses LabRole and depends on the laboratory's availability.


Group observers can register and browse the same group profiles without connecting
Spotify. Register an observer with `scripts/allow_dashboard_member.py --user-id pati
--email <approved-email> --viewer --name Pati`. Observers use `VIEWER#` membership
records and are excluded from Spotify collection and listening rankings. The profile
selector allows every group member to view the group's individual listening summaries.


## Weekly Wrapped generation

`infra/wrapped` deploys a Standard Step Functions workflow and an EventBridge
Scheduler schedule for Mondays at 09:00 Europe/Madrid. Each run summarizes the
previous complete Monday–Sunday week, then archives HTML and PDF reports in the private
raw bucket under `wrapped/group=<group>/week=<monday>/`. The workflow passes only
object references between tasks. Conditional writes preserve the original snapshot
and report across retries. The execution start time fixes week selection during retries.

```bash
terraform -chdir=infra/wrapped init -backend-config=../envs/dev/backend.conf -backend-config="key=dev/wrapped.tfstate"
bash scripts/build_wrapped_package.sh
terraform -chdir=infra/wrapped plan
terraform -chdir=infra/wrapped apply
```

An authenticated group member or observer can download the last complete week's
PDF report from the dashboard. After successful archival, a third workflow step publishes an availability notice through
the dedicated Wrapped SNS topic. Downloading the PDF does not send a notice. SES account
and identity configuration queries were denied in the current Academy session;
personalized email delivery remains pending. The schedule depends on Academy availability.


The account label always identifies the signed-in member. Selecting a friend's profile
changes the statistics and heading while retaining that account label. Observers use
their own account name and can inspect the group's Spotify profiles. Wrapped PDFs
are generated with ReportLab in a Lambda package built for Python 3.13 on Linux x86_64;
run the package build before planning changes to the Wrapped deployment.


GitHub Actions validates ingestion, connection, dashboard, Wrapped, analytics and
concerts stacks. Academy PR plans and release deployments use separate state keys
for each stack. PDF dependencies are built before planning or deploying the Wrapped
function. AWS repository variables and expiring Academy credentials must be configured
before cloud plans and deployments can run; local source publication alone runs CI.

## Delivery status — 20 November 2026

- Working MVP in Academy: three Spotify listeners, invitation-based onboarding, Cognito sign-in, group and observer access, profile/month filters, weekly group rankings and private PDF downloads.
- Weekly workflow: prepare snapshot -> archive PDF -> SNS availability notice. A real notice was received by the owner; repeating the workflow reused the publication receipt without rewriting the PDF.
- Analytics: private Glue catalog and three working Athena queries over raw S3 JSON, checked against an independent reconstruction and a duplicate-input test.
- Monitoring: API errors/latency alarms, function error alarms, operations dashboard and service tracing configuration. The latest full application test suite has 106 passing tests; CI also validates Terraform and runs Trivy.
- Concerts: search/cache infrastructure and web section prepared, schedule disabled. Ticketmaster Developer approval is still pending, so live results and concert alerts are not part of the verified MVP.

### Accepted limitations and excluded extensions

- Collection depends on Academy availability; Spotify does not guarantee recovering all history after an interruption. Existing collection behavior is retained for this delivery.
- SNS is the chosen email solution: a link requiring sign-in, without a PDF attachment or personalized SES email. SES configuration was denied by the lab and is not pursued for this delivery.
- Active X-Ray configuration and trace IDs were checked, but `xray:GetTraceSummaries` is denied; detailed trace segments remain unreviewed.
- `bedrock:ListFoundationModels` was denied. Bedrock summaries were not implemented; model invocation permissions were not separately established.
- Creating the GitHub OIDC provider (`iam:CreateOpenIDConnectProvider`) was denied. OIDC roles and optional own-account `prod` ingestion remain prepared configuration, not deployed resources. No separate production account was opened.
- GitHub CI is working. Automatic AWS PR plans and cloud deployments remain unconfigured; saved local Terraform plans must not be described as automatic PR plans.
- Parquet/Glue ETL is an optional future extension. The implemented catalog/query layer reads JSON directly; it is not a curated Parquet pipeline.

## Parameters for Academy application stacks

Resource names retain their current defaults (`sfw-dev`, `LabRole`, `friends`) so
parameterization alone does not rename existing resources. Each application stack
accepts `aws_region`, `name_prefix`, `lab_role_name`, `table_name` and `group_id`.
Dashboard and Wrapped require `raw_bucket_name`; All three stacks require
`alarm_topic_arn`. Supply real values locally or obtain them from ingestion outputs:

```bash
export TF_VAR_raw_bucket_name="$(terraform -chdir=infra/envs/dev output -raw raw_bucket)"
export TF_VAR_table_name="$(terraform -chdir=infra/envs/dev output -raw table_name)"
export TF_VAR_group_id="$(terraform -chdir=infra/envs/dev output -raw group_id)"
export TF_VAR_alarm_topic_arn="$(terraform -chdir=infra/envs/dev output -raw alarm_topic_arn)"
export TF_VAR_dashboard_url="$(terraform -chdir=infra/dashboard output -raw dashboard_url)"
```

The new alarm output requires an ingestion apply/refresh-only apply reviewed against
its existing state before downstream automation reads it. Inspect every cloud plan;
never accept resource replacement merely to adopt these parameters. These source
changes have not been applied to the live Academy deployment.

## API observability

The connection and dashboard stacks define HTTP API `5xx` alarms and p95 latency
alarms (3 seconds in two of three five-minute windows). Missing data is not a failure;
latency alarms ignore low-sample percentile windows, appropriate for this small group.
All application functions have error alarms routed to the existing SNS topic. The
`sfw-dev-operations` CloudWatch dashboard shows web request counts, errors and latency,
and errors/throttles for the application functions. These use standard API metrics rather
than additional per-route metrics.

Active X-Ray tracing is configured for all application Lambdas and the weekly state
machine. This provides service-level segments; it does not automatically instrument
Python SDK or Spotify HTTP calls. HTTP APIs do not provide the REST API X-Ray stage
setting. Inspect actual trace segments before claiming complete end-to-end coverage.
Tracing requires the existing LabRole to permit X-Ray writes. Alerts, metrics and
trace storage may incur usage charges; availability still depends on Academy.

The current Academy identity denies `xray:GetTraceSummaries`; a full review of trace
segments remains pending access. Configuration and Lambda log reports can be checked
separately and must not be presented as proof of full trace ingestion.

## Raw archive analytics (Glue and Athena)

`infra/analytics` manages an independent catalog/query layer, with state key
`dev/analytics.tfstate`. The data flow is S3 raw JSON -> Glue Data Catalog -> Athena SQL.
It does not modify ingestion, DynamoDB or the hosted application. All results remain
private under `analytics-results/` in the existing bucket and are encrypted with SSE-S3.
The enforced workgroup cutoff is 100 MiB scanned per query, not a total spending cap.

```bash
terraform -chdir=infra/analytics init -backend-config=../envs/dev/backend.conf -backend-config="key=dev/analytics.tfstate"
# Set TF_VAR_raw_bucket_name from the existing ingestion raw_bucket output.
terraform -chdir=infra/analytics plan
terraform -chdir=infra/analytics apply
.venv/bin/python scripts/query_analytics.py --query counts --start-date 2026-11-01 --end-date 2026-11-20
.venv/bin/python scripts/query_analytics.py --query top_artists --start-date 2026-11-01 --end-date 2026-11-20
.venv/bin/python scripts/query_analytics.py --query monthly --start-date 2026-11-01 --end-date 2026-11-20
```

Use the dates covering the archived collections you want to inspect. The dates are
inclusive and filter UTC collection partitions; they are not filters on playback time.
Monthly results group actual playback timestamps in Europe/Madrid. Minutes are full
track-duration estimates. The hosted dashboard also offers its own monthly filter over operational DynamoDB records.

In the AWS Athena console select workgroup `sfw-dev-analytics`, database
`sfw_dev_analytics` and a saved query. Queries deduplicate overlapping pages while
preserving repeat plays at different times. A collaboration counts for each distinct
credited artist; credited artist totals can therefore exceed the number of plays.
Raw-derived totals may differ from operational DynamoDB counts because archived pages
can include playback context outside a collection checkpoint. Compare like-for-like
sources before interpreting differences as missing data.

Listener partitions are configured through `listener_ids`; update that list when a new
Spotify listener joins. Observers need no partition. The current schema covers raw
Spotify responses, not imported export files. There is no crawler, Glue ETL job or
curated Parquet layer in this implementation. See decision [009](decisions/009-raw-analytics-catalog.md).

## Monthly profile filter

Choose **Por mes**, then select a month. Counts, estimated minutes, songs and artists
use that calendar month in Europe/Madrid; month start is inclusive and next-month
start exclusive. The current month ends at the request time. Future and malformed
months return HTTP 400. The selected profile still must belong to the signed-in
user's group; observers retain their existing access. The weekly group ranking
continues to describe the current week independently of the profile filter.

This web filter queries DynamoDB, rather than starting paid Athena queries for each
page refresh. Athena remains a separate analytical view of archived response pages.
The local preview shares the same calendar-range helper. `PREVIEW_PORT` optionally
selects a different loopback port for independent preview sessions.

## Wrapped availability notices

The weekly workflow now prepares, archives and then notifies. `infra/wrapped` requires
`dashboard_url`, obtained from the existing dashboard output. A notice links to the
web home page; users sign in before downloading the private PDF. It contains the week
and link, without an attachment or listening details. Set `TF_VAR_wrapped_notice_emails` to a JSON array of opted-in email addresses in the deploying environment. Use the same list for future applies. Each recipient must confirm the SNS subscription. Friends and teachers are not subscribed by
being registered in the application.

A per-group/week DynamoDB receipt suppresses repeated completed publishes. Conditional
leases prevent simultaneous sends and permit recovery after a crash. This reduces
application duplicates, but standard SNS and a failure between publishing and saving
the receipt can still produce duplicate emails. `published` records SNS acceptance,
not proof of inbox delivery. Historical backfills skip the notice because the current
download route serves the latest complete week. SNS failures leave the archived PDF
intact and are reported through the existing workflow failure alarm.

For GitHub deployments set the WRAPPED_NOTICE_EMAILS secret to the same JSON array.
The Wrapped Lambda role needs permission to publish to the dedicated encrypted topic,
including access to the SNS KMS key. Confirm delivery before relying on weekly notices.
To enable the optional scheduler DLQ, verify LabRole has sqs:SendMessage on
<name_prefix>-wrapped-scheduler-dlq, then set TF_VAR_scheduler_dlq_enabled=true
(or the SCHEDULER_DLQ_ENABLED repository variable). Its CloudWatch alarm uses
the operations topic. This detects exhausted target delivery attempts. See decision
[010](decisions/010-wrapped-availability-notice.md).

## Concert discovery preparation

Ticketmaster approval remains pending. `infra/concerts` prepares the Lambda, logs,
error alarm and a daily 09:15 Europe/Madrid schedule, **disabled by default**. The
protected `/api/concerts` route displays a clear not-activated state. There are no
fabricated concerts and no live Discovery validation yet.

The scanner considers the top five artists per listener over 30 days, searches future
music events across Spain, matches attraction names and publishes a complete cache
generation only after all queries and writes succeed. A failed scan preserves the
previous result. A successful empty scan correctly hides old matches. The UI shows
last-scan age; events and availability must be checked at the provider. Access uses
the signed-in group, never a group ID supplied in the URL.

After Ticketmaster approval:

1. Run `.venv/bin/python scripts/configure_ticketmaster.py` locally and enter the key
   at the hidden prompt. Do not place it in GitHub, Terraform state or chat.
2. Deploy/review the concerts stack with existing table, group and alarm parameters,
   using independent state key `dev/concerts.tfstate`.
3. Run one real Lambda scan and review coverage, errors and cached results.
4. Set `concerts_enabled=true` for both the concerts and dashboard stacks. If cloud
   workflows are configured, also persist repository variable `CONCERTS_ENABLED=true`.

The default secret identifier is `<name_prefix>/ticketmaster`. No key is created by
Terraform. The existing key-configuration script targets `sfw-dev/ticketmaster`.
This layer does not send new-concert email alerts yet; those remain a follow-up after
live provider validation. Old scan generations currently remain in DynamoDB. See
[decision 011](decisions/011-concert-discovery.md).
