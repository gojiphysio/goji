"""
The agent's knowledge base, built from the website's own content so a price or
service change on the site reaches the agent at the next deploy, and the agent
never knows anything the site doesn't say.

  core   always in the system prompt (cached), kept small because every
         request pays for it: llms.txt, one line per service, a summary per
         clinician, an index of pages (~8K tokens)
  pages  full service, team, condition and blog pages, fetched on demand by
         the read_page tool

Build (deploy.sh does this before every deploy; output is gitignored):
  python -m wa_agent.kb --site ../../marketing/website --out wa_agent/_build/kb.json
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from . import config

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.S)


def _split(md: str) -> tuple[str, str]:
    m = FRONTMATTER.match(md)
    return (m.group(1), m.group(2)) if m else ("", md)


def _field(front: str, key: str) -> str:
    m = re.search(rf'^{key}:\s*"?(.*?)"?\s*$', front, re.M)
    return m.group(1) if m else ""


def _is_draft(front: str) -> bool:
    return bool(re.search(r"^draft:\s*true\s*$", front, re.M))


def _list(front: str, key: str) -> list[str]:
    m = re.search(rf"^{key}:\s*\[(.*?)\]\s*$", front, re.M)
    return re.findall(r'"([^"]+)"', m.group(1)) if m else []


def _specialties(front: str) -> list[str]:
    """`specialties:` list items as "Title: description"."""
    block = re.search(r"^specialties:\n((?:[ \t].*\n?)*)", front, re.M)
    if not block:
        return []
    items = re.findall(r'-\s*title:\s*"?(.*?)"?\s*\n\s*description:\s*"?(.*?)"?\s*$',
                       block.group(1), re.M)
    return [f"{t}: {d}" for t, d in items]


def _service_line(stem: str, front: str) -> str:
    price = f"${_field(front, 'priceClinic')} in clinic"
    if _field(front, "priceHome"):
        price += f", ${_field(front, 'priceHome')} home visit"
    booking = _field(front, "bookingService")
    if _field(front, "bookingFocus"):
        booking += f" / focus {_field(front, 'bookingFocus')}"
    return (f"- {_field(front, 'title')} ({_field(front, 'category')}): "
            f"{_field(front, 'durationMin')} min, {price}. "
            f"Clinicians: {', '.join(_list(front, 'clinicians'))}. "
            f"Booking tool service: {booking}. {_field(front, 'cardLead')} "
            f"[read_page services/{stem}]")


def build(site: Path) -> dict:
    """Compact always-on core (~8K tokens) + full pages behind read_page.

    The core is what every request pays for, so it holds only what most
    questions need: llms.txt (the clinic's own fact sheet), one line per
    service, a short summary per clinician, and an index of every page."""
    content = site / "src" / "content"
    pages: dict[str, str] = {}
    services, team, index = [], [], []

    for kind in ("services", "team", "conditions", "blog"):
        for f in sorted((content / kind).glob("*.md")):
            front, body = _split(f.read_text())
            if _is_draft(front):
                continue
            page_id = f"{kind}/{f.stem}"
            url = f"{config.SITE_BASE}/{kind}/{f.stem}/"
            title = _field(front, "title") or _field(front, "name")
            # services/team keep their frontmatter: FAQs and bios live there
            text = f.read_text() if kind in ("services", "team") else body.strip()
            pages[page_id] = f"# {title}\n{url}\n\n{text}\n"
            if kind == "services":
                services.append(_service_line(f.stem, front))
            elif kind == "team":
                team.append(f"- {title}, {_field(front, 'role')} ({_field(front, 'credentials')}). "
                            + " | ".join(_specialties(front)) + f" [read_page {page_id}]")
            else:
                index.append(f"- {page_id}: {title}")

    house = Path(__file__).with_name("house_rules.md")
    core = "\n".join([
        "# Goji clinic facts (llms.txt)\n", (site / "public" / "llms.txt").read_text(),
        "\n" + (house.read_text() if house.exists() else ""),
        "\n# Services (prices per session; full page with FAQs via read_page)",
        *services,
        "\n# Clinicians (full bio via read_page)",
        *team,
        "\n# Condition and blog pages (read_page with the id before answering from them)",
        *index,
    ])
    return {"core": core + "\n", "pages": pages}


_loaded: dict | None = None


def load(path: str = config.KB_PATH) -> dict:
    global _loaded
    if _loaded is None:
        _loaded = json.loads(Path(path).read_text())
    return _loaded


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--site", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    kb = build(args.site)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(kb))
    print(f"kb: core {len(kb['core']):,} chars, {len(kb['pages'])} pages -> {args.out}")


if __name__ == "__main__":
    main()
