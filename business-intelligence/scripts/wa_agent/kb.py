"""
The agent's knowledge base, built from the website's own content so a price or
service change on the site reaches the agent at the next deploy, and the agent
never knows anything the site doesn't say.

  core   always in the system prompt (cached): llms.txt, every service page,
         every team bio, and an index of condition and blog pages
  pages  condition and blog bodies, fetched on demand by the read_page tool

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


def build(site: Path) -> dict:
    content = site / "src" / "content"
    parts = ["# Goji clinic facts (from llms.txt)\n", (site / "public" / "llms.txt").read_text()]

    parts.append("\n\n# Service pages (prices, durations, clinicians, FAQs)\n")
    for f in sorted((content / "services").glob("*.md")):
        md = f.read_text()
        front, _ = _split(md)
        if _is_draft(front):
            continue
        parts.append(f"\n## services/{f.stem}  ({config.SITE_BASE}/services/{f.stem}/)\n{md}\n")

    parts.append("\n\n# Team\n")
    for f in sorted((content / "team").glob("*.md")):
        parts.append(f"\n## team/{f.stem}  ({config.SITE_BASE}/team/{f.stem}/)\n{f.read_text()}\n")

    pages: dict[str, str] = {}
    index = ["\n\n# Other pages (call read_page with the id for the full text)\n"]
    for kind in ("conditions", "blog"):
        for f in sorted((content / kind).glob("*.md")):
            front, body = _split(f.read_text())
            if _is_draft(front):
                continue
            page_id = f"{kind}/{f.stem}"
            url = f"{config.SITE_BASE}/{kind}/{f.stem}/"
            pages[page_id] = f"# {_field(front, 'title')}\n{url}\n\n{body.strip()}\n"
            index.append(f"- {page_id}: {_field(front, 'title')} - {_field(front, 'cardLead')}")
    parts.extend(index)
    return {"core": "".join(parts) + "\n", "pages": pages}


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
