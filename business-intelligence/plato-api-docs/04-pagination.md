# Plato API - Pagination

Source: https://clinic.platomedical.com/developers/1.0/api_page
Captured: 2026-05-23

---

API calls expose a query variable `current_page`. This variable can be used to paginate through records.

Your loop logic could be to keep looping till you get an empty record set. A sample pseudo-code:

```python
# sample pseudo code
i = 1
while True:
    records = get_records_for_page(i)
    if len(records) == 0:
        break
    i += 1
    sleep(1)
```

## Notes for Goji BI

- Combined with the rate-limit doc: each page returns up to 20 records, with a per-minute rate limit. Plan sleep intervals accordingly.
- Pair `current_page` with the `modified_since` parameter (see rate-limiting doc) for incremental syncs - dramatically reduces API spend.
