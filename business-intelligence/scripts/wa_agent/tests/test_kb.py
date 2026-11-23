from wa_agent import kb

from .conftest import SITE


def test_core_carries_prices_services_and_team():
    core = kb.build(SITE)["core"]
    assert "$260" in core and "$380" in core           # from llms.txt / service pages
    assert "services/pelvic-floor-physiotherapy" in core
    assert "team/claire-ng" in core
    assert "8377 0401" in core                          # clinic phone, from llms.txt


def test_pages_are_indexed_and_fetchable():
    built = kb.build(SITE)
    assert "conditions/diastasis-recti" in built["pages"]
    assert "- conditions/diastasis-recti:" in built["core"]
    assert any(p.startswith("blog/") for p in built["pages"])


def test_core_stays_small():
    # Every request pays for the core (and the first after an idle hour pays
    # a 2x cache write), so it holds summaries; full pages go via read_page.
    # ~4 chars/token: under ~10K tokens.
    assert len(kb.build(SITE)["core"]) < 40_000


def test_service_lines_carry_price_duration_and_booking_id():
    core = kb.build(SITE)["core"]
    line = next(l for l in core.splitlines() if l.startswith("- Pelvic Floor Physiotherapy"))
    assert "55 min" in line and "$260 in clinic" in line and "$380 home visit" in line
    assert "physiotherapy / focus womens-health" in line
    assert "read_page services/pelvic-floor-physiotherapy" in line


def test_full_service_and_team_pages_are_fetchable():
    pages = kb.build(SITE)["pages"]
    assert "Does the assessment involve an internal examination?" in \
        pages["services/pelvic-floor-physiotherapy"]
    assert "Kristy" in pages["team/kristy-ng"]
