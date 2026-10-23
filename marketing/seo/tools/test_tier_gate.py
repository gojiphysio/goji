"""Tests for tier_gate.py: each case builds a throwaway git repo with one change.

Run: python3 -m unittest marketing/seo/tools/test_tier_gate.py
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GATE = Path(__file__).resolve().parent / "tier_gate.py"
SITE = "marketing/website/prototype/"
COND = SITE + "src/content/conditions/diastasis-recti.md"
BASE_FILES = {
    COND: "---\ndescription: Old description.\nreviewer: { name: Cheryl Long, slug: cheryl-long }\n---\nBody text about the abdominal wall.\n",
    SITE + "src/pages/book.astro": "<form></form>\n",
    SITE + "public/llms.txt": "# Goji\n",
    ".github/workflows/x.yml": "on: push\n",
}


def run(changes, labels=""):
    with tempfile.TemporaryDirectory() as d:
        def git(*a):
            subprocess.run(["git", *a], cwd=d, check=True, capture_output=True)
        git("init", "-q", "-b", "main")
        git("config", "user.email", "t@t")
        git("config", "user.name", "t")
        for p, c in BASE_FILES.items():
            (Path(d) / p).parent.mkdir(parents=True, exist_ok=True)
            (Path(d) / p).write_text(c)
        git("add", "-A")
        git("commit", "-qm", "base")
        git("checkout", "-qb", "feature")
        for p, c in changes.items():
            (Path(d) / p).parent.mkdir(parents=True, exist_ok=True)
            (Path(d) / p).write_text(c)
        git("add", "-A")
        git("commit", "-qm", "change")
        env = {k: v for k, v in os.environ.items() if not k.startswith("GITHUB_")}
        r = subprocess.run([sys.executable, str(GATE), "--base", "main", "--labels", labels],
                           cwd=d, capture_output=True, text=True, env=env)
        tier = r.stdout.split("tier ", 1)[1][0]
        return tier, r.returncode, r.stdout


def edit_cond(old, new):
    return {COND: BASE_FILES[COND].replace(old, new)}


class TierGate(unittest.TestCase):
    def test_reword_reviewed_copy_is_a(self):
        tier, code, _ = run(edit_cond("Old description.", "A shorter, clearer description."), "tier-a")
        self.assertEqual((tier, code), ("A", 0))

    def test_llms_txt_is_a(self):
        self.assertEqual(run({SITE + "public/llms.txt": "# Goji\n- page\n"})[0], "A")

    def test_new_content_page_is_b(self):
        self.assertEqual(run({SITE + "src/content/conditions/new.md": "---\n---\nx\n"})[0], "B")

    def test_superlative_is_b(self):
        self.assertEqual(run(edit_cond("Body text", "The best body text"))[0], "B")

    def test_cure_claim_is_b(self):
        self.assertEqual(run(edit_cond("Body text", "Physio cures this. Body text"))[0], "B")

    def test_new_time_claim_is_b(self):
        self.assertEqual(run(edit_cond("Body text", "Most improve in 6 weeks. Body text"))[0], "B")

    def test_reviewer_change_is_b(self):
        self.assertEqual(run(edit_cond("cheryl-long }", "kristy-ng }"))[0], "B")

    def test_new_price_is_c(self):
        self.assertEqual(run(edit_cond("Body text", "Now $999. Body text"))[0], "C")

    def test_booking_is_c(self):
        self.assertEqual(run({SITE + "src/pages/book.astro": "<form>x</form>\n"})[0], "C")

    def test_ci_is_c(self):
        self.assertEqual(run({".github/workflows/x.yml": "on: pull_request\n"})[0], "C")

    def test_outside_site_is_c(self):
        self.assertEqual(run({"business-intelligence/app.py": "x\n"})[0], "C")

    def test_mislabelled_tier_a_fails(self):
        tier, code, _ = run({SITE + "src/pages/book.astro": "<form>x</form>\n"}, "tier-a")
        self.assertEqual((tier, code), ("C", 1))

    def test_unlabelled_c_reports_without_failing(self):
        self.assertEqual(run({SITE + "src/pages/book.astro": "<form>x</form>\n"})[1], 0)


if __name__ == "__main__":
    unittest.main()
