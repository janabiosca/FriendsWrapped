# 011 · Prepare bounded daily concert discovery, disabled until provider approval

**Context.** The group wants upcoming concerts across Spain for its listening
preferences. Ticketmaster Developer approval is still pending, so no real API key or
live Discovery results have been validated. A placeholder must not look like real data.

**Decision.** Prepare an independent concerts Lambda and daily EventBridge Scheduler
schedule at 09:15 Europe/Madrid, disabled by default. Add a protected read-only cache
route and a dashboard section that clearly states when discovery is not activated.
Only store the secret identifier in function configuration; the key is validated and
written separately by `scripts/configure_ticketmaster.py` using hidden input.

Select the five most listened-to artist names per Spotify member over 30 days. Match
normalized attraction names exactly, query future music events in ES, and verify the
embedded event attraction again to exclude simple tribute/keyword mismatches. Reject
cancelled, postponed, past, undated and non-Spanish events. Keep venue time zones,
including Canary Islands dates. Only trusted HTTPS Ticketmaster .es/.com links are
shown; other event links are omitted. Names are rendered as text in the browser.

Use bounded pages and pace requests below the documented default per-second quota.
A provider error or pagination ceiling fails rather than claiming complete coverage.
Errors must never expose URLs containing the key. Discovery coverage is not exhaustive;
exact normalized names can still be ambiguous for artists sharing a name.

Write immutable scan generations first, then conditionally publish a current-scan
pointer. Failed or partial writes do not overwrite the previous generation. An older
scan cannot replace a newer pointer. Readers paginate only the referenced generation,
exclude events that have passed, and flag results older than 48 hours. The existing
Lambda error alarm reports scan failures. Old generations are retained for now;
a retention policy is future work if scan volume warrants it.

**Activation gate.** The current deployment is preparation only: `concerts_enabled`
is false, there is no automatic remote scan, and no fabricated events are shown. After
approval, store a valid key, run and inspect a real scan, then enable both the schedule
and dashboard with Terraform and persist `CONCERTS_ENABLED=true` in configured CI.
Live provider correctness, account quotas and coverage remain unverified until then.
Concert availability notifications are not included in this initial search/cache layer.

Reference: [Ticketmaster Discovery API](https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/).
