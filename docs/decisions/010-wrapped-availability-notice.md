# 010 · Notify availability through a dedicated SNS topic

**Context.** SES account and identity configuration is denied in the current Academy
session. The owner already has one confirmed email subscription to the operations
SNS topic. Reports are private and downloaded after group authentication.

**Decision.** Append `NotifyWeeklyWrapped` after successful report archival in the
Standard Step Functions workflow. The same Wrapped Lambda publishes a plain text
notice with the week and authenticated dashboard URL to the dedicated Wrapped SNS topic. Operations alarms use a separate topic.

Validate the ready manifest against the configured group and confirm the PDF exists.
Skip notices for historical weeks because the dashboard downloads the last complete
week. Require a configured HTTPS home URL rather than accepting a destination from
workflow input. Pass the existing dashboard output into Terraform as `dashboard_url`.

A DynamoDB record at `GROUP#<group> / WRAPPED_NOTICE#<week>` claims an expiring lease
before publishing. Other concurrent attempts fail and retry. A completed publication
stores the SNS MessageId and suppresses later application-level publishes for that
week. An abandoned lease expires after 180 seconds, longer than the Lambda timeout;
workflow retry delays allow recovery. Failed publishes leave retryable state.

**Delivery limits.** SNS Publish success means accepted, not confirmed inbox delivery.
DynamoDB and SNS do not share an atomic transaction: a timeout after SNS acceptance,
or a crash before persisting the receipt, can cause a later duplicate. Standard SNS
can also redeliver. This implementation reduces duplicates but does not provide
exactly-once email delivery. A failed notifier does not delete or rewrite the report;
the workflow failure alarm signals the issue while the PDF remains downloadable.

**Recipients.** Configure opted-in addresses with `wrapped_notice_emails`. Each recipient confirms their subscription. Cognito registration does not subscribe users.

References: [SNS delivery retries](https://docs.aws.amazon.com/sns/latest/dg/sns-message-delivery-retries.html).
