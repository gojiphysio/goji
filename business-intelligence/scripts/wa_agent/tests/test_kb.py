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


def test_core_fits_comfortably_in_one_cached_prompt():
    # ~4 chars/token: keep the always-on context under ~60K tokens.
    assert len(kb.build(SITE)["core"]) < 240_000
