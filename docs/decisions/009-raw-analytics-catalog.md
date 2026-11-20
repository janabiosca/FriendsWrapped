# 009 · Query the raw archive with Glue Data Catalog and Athena

**Context.** DynamoDB supports the operational dashboard, while S3 retains complete
Spotify response pages. Analytical SQL should read these archives without affecting
the collector or making listening data public. Repeated response pages can overlap.

**Decision.** An independent `infra/analytics` stack creates a Glue database, a nested
JSON external table, an Athena workgroup and three saved SQL queries. The existing
private ingestion bucket holds source data and encrypted query results in separate
prefixes. No new IAM role, crawler or continuously running process is required.

Partition projection maps listener and UTC collection date onto the existing Hive-style
S3 paths. A configurable listener list excludes observers, who have no Spotify data.
The date range starts at the configured first archive day. Queries flatten `items`
and deduplicate by listener, playback timestamp and track identity. Repeated plays
of the same song at different times remain separate. Collaborations count once per
distinct credited artist name, matching the operational statistics convention.

Use Hive JSON SerDe rather than OpenX because AWS documents potentially
non-deterministic row counts with OpenX. Source objects must contain one JSON document
per line; `store.archive_raw` currently writes one single-line JSON page per object.
Invalid input should fail the query rather than silently dropping records.

The workgroup enforces encrypted results and a 100 MiB per-query scan cutoff. This is
not an overall spending cap. The query script cancels a query when its waiting timeout
expires; it does not silently leave long-running work behind. Use date predicates to
prune collection partitions. Results remain private in the existing bucket.

**Limitations.** Archive dates describe collection, not listening dates. Monthly SQL
uses actual playback timestamps in Europe/Madrid. A seed page may contain earlier
plays. Raw response pages may contain context outside an operational checkpoint, so
raw-derived totals are not automatically identical to DynamoDB totals. This analysis
cannot recover plays Spotify never returned. Minutes are full-track estimates; they
are not measured listening or skip time. Imported exports are not part of this raw
Spotify response table. The catalog has no per-group end-user authorization layer;
access is through authorized AWS identities and is not exposed in the web app.

This is a catalog and query layer, not a Glue ETL job or a curated Parquet zone.
A later transformation can be evaluated against measured query volume and needs.

References: [partition projection](https://docs.aws.amazon.com/athena/latest/ug/partition-projection-setting-up.html),
[Hive JSON SerDe](https://docs.aws.amazon.com/athena/latest/ug/hive-json-serde.html),
[OpenX limitations](https://docs.aws.amazon.com/athena/latest/ug/openx-json-serde.html).

## Deployment validation (20 November 2026)

All three queries succeeded against the real archive and agreed with an independent
Python reconstruction of 89 S3 objects. An additional live SQL fixture duplicated
all source rows with `UNION ALL`; deduplicated counts remained unchanged. No fixture
objects were written to the raw archive. Per-query scan volume was below 1 MiB for
the baseline queries at validation time. Source collection can continue afterward.
