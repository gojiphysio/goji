"""Hermetic test setup: memory state, no BigQuery/SMTP/network, a KB built
from the repo's own website content, no real pre-send wait."""
import os
from pathlib import Path

os.environ.setdefault("WA_AGENT_STATE", "memory")
os.environ.setdefault("WA_AGENT_LOG_EVENTS", "false")
os.environ.setdefault("WA_APP_SECRET", "test-secret")
os.environ.setdefault("WA_VERIFY_TOKEN", "verify-me")
os.environ.setdefault("WA_AGENT_ADMIN_TOKEN", "admin-token")
os.environ.setdefault("GMAIL_APP_PASSWORD", "")

import pytest  # noqa: E402

from wa_agent import kb  # noqa: E402

SITE = Path(__file__).resolve().parents[4] / "marketing" / "website"


@pytest.fixture(scope="session", autouse=True)
def _kb():
    kb._loaded = kb.build(SITE)
    yield
    kb._loaded = None
