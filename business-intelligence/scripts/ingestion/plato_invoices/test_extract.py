"""recent_only stops paging once a full page of invoices is older than the cutoff."""
from main import recent_only


def _inv(day):
    return {"date": f"{day} 10:00:00"}


def test_stops_after_a_full_page_of_old_invoices():
    rows = [_inv("2026-10-27")] * 5 + [_inv("2026-09-01")] * 50
    out = list(recent_only(iter(rows), "2026-10-13", page_size=20))
    assert len(out) == 25  # 5 recent + one page of old, then stop


def test_a_recent_invoice_resets_the_count():
    rows = [_inv("2026-09-01")] * 19 + [_inv("2026-10-20")] + [_inv("2026-09-01")] * 30
    out = list(recent_only(iter(rows), "2026-10-13", page_size=20))
    assert len(out) == 40


def test_undated_rows_never_count_as_old():
    rows = [{"date": None}] * 30
    assert len(list(recent_only(iter(rows), "2026-10-13", page_size=20))) == 30


def test_no_cutoff_is_a_full_sweep():
    rows = [_inv("2020-01-01")] * 100
    assert len(list(recent_only(iter(rows), None))) == 100


def test_stopping_requests_no_further_pages():
    fetched = []

    def pages():
        for p in range(10):
            fetched.append(p)
            yield from [_inv("2020-01-01")] * 20

    list(recent_only(pages(), "2026-10-13", page_size=20))
    assert fetched == [0]
