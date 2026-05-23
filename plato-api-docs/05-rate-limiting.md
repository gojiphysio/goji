# Plato API - Rate Limiting

Source: https://clinic.platomedical.com/developers/1.0/api_rate
Captured: 2026-05-23

---

To prevent abuse, Plato institutes a rate limit of a fixed number of API requests every minute. Each API request can fetch up to 20 records. (Check your limit at "System Setup" -> "General Settings" -> "API".) With an API limit of 20 req/min, you can fetch up to 576,000 records per day.

If your database exceeds the rate limit, this will result in an HTTP 429 (too many requests) response. The API also returns `x-ratelimit-limit` and `x-ratelimit-remaining` headers to help you manage your requests.

If you need more throughput, you can upgrade your rate limit from "System Setup" -> "General Settings" -> "API".

## Best practices for using Plato's API

- Use the `modified_since` parameter to only query data that has been modified in the last X seconds. This will reduce the number of calls needed.
- Use central querying and caching. If you have multiple modules requesting the same data - cache that data locally.
- Track `x-ratelimit-limit` and `x-ratelimit-remaining` headers returned by Plato's API to throttle the requests.
- Use an exponential backoff strategy for requests that fail.

## Notes for Goji BI

- Our ingestion strategy fits naturally: a single Cloud Run job per resource, scheduled hourly, using `modified_since` to pull only what's changed since the last successful run. Store last-success timestamp in a small BQ control table or in Cloud Run secret metadata.
- Read the `x-ratelimit-remaining` header after each call; if low, `sleep` until the next minute window.
- Implement exponential backoff on 429 and 5xx (e.g. 1s, 2s, 4s, 8s, capped at 60s).
- 20 records per page x 20 req/min = 400 records/min worst case. A single-site physio clinic generates maybe 100 appointments/day, well within limits.
