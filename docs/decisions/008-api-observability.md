# 008 · Monitor API errors and latency, and trace application services

**Context.** Collection alarms alone cannot detect an unavailable dashboard or broken
Spotify onboarding. The group generates sparse traffic and Academy can be unavailable.

**Decision.** Monitor HTTP API `5xx` counts and p95 `Latency` at API/stage scope. Alert
on a server error within five minutes, and on latency above 3000 ms in two of three
five-minute windows. Missing traffic is not an error; low-sample percentile windows
are ignored. Keep client `4xx` responses out of the server-error alarm: expired tokens
and rejected invitations are expected client failures.

Each application Lambda has an `Errors` alarm using the existing SNS subscription.
One operations dashboard shows web traffic and latency, plus errors/throttles across
all six functions. Enable Active tracing on application Lambdas and tracing on the
Standard weekly state machine. Keep the current sampling configuration.

**Alternatives.** Per-route detailed metrics add cost and are unnecessary at this
scale. A missing-requests alarm would alert whenever nobody uses the application.
A synthetic monitor may be useful later but has not been implemented.

**Consequences.** API metrics, alarms, dashboards and traces may incur costs. Alarms
react to actual traffic rather than continuously proving availability. Service-level
tracing does not instrument Spotify HTTP requests or Python SDK calls automatically.
The Academy session permits configuration changes but denies `xray:GetTraceSummaries`;
reading actual trace segments cannot be verified with that identity. Do not describe
configured tracing as a verified complete distributed trace.

References: [HTTP API metrics](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-metrics.html),
[Step Functions tracing](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-xray-tracing.html).
