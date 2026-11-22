# Friends Wrapped

A Cloud Solutions university project that turns Spotify listening history into shared music statistics for a group of friends.

## What it does

- Collects listening activity from three Spotify accounts every five minutes while the lab services are running.
- Shows individual profiles, monthly statistics and a weekly group ranking.
- Lets approved observers browse the group without connecting Spotify.
- Generates a weekly PDF and emails an availability notice to the group through SNS.
- Supports SQL analysis of the archived data with Glue Data Catalog and Athena.

## Try the app

[Open Friends Wrapped](https://9f3a4fzus4.execute-api.us-east-1.amazonaws.com/)

Registration is restricted to approved email addresses. Choose **Sign up**, create a password and verify your email. Availability depends on the AWS Academy laboratory.

## How it works

```text
EventBridge -> Lambda dispatcher -> SQS -> Lambda collector -> DynamoDB + S3
Cognito + API Gateway -> authenticated group dashboard
Step Functions -> weekly PDF in private S3 -> SNS availability notice
S3 raw archive -> Glue Data Catalog -> Athena SQL
```

Infrastructure is managed with Terraform, and account-specific values are configuration, so the same code deploys to another account. GitHub Actions runs Python tests, Terraform checks and Trivy security scans on every pull request. The release workflow is prepared but not configured: AWS deployments use reviewed local plans.

## Current limitations

- Lab interruptions can create gaps that Spotify's available history cannot always recover.
- Listening minutes are estimates based on track durations.
- Ticketmaster integration is prepared but disabled pending Developer account approval; live concerts and concert alerts are not verified.
- SNS sends a link rather than an attached PDF: SNS email has no attachments and SES is blocked in AWS Academy. The PDF stays behind sign-in.
- Detailed X-Ray review and OIDC setup are restricted by lab permissions. A separate production environment has not been deployed.

## Code and documentation

- `src/`: application and Lambda code.
- `infra/`: Terraform infrastructure.
- `web/`: dashboard interface.
- `tests/`: automated tests.
- `scripts/`: setup and administration tools.
- [Technical and deployment guide](docs/deployment-guide.md).
- [Architecture decisions](docs/decisions/README.md).

Credentials, tokens, personal configuration and Terraform state are excluded from the repository.
