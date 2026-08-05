from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SITE_ROOT = PROJECT_ROOT / "site"


class StartTagCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.tags.append((tag, dict(attrs)))


class SiteSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (SITE_ROOT / "index.html").read_text(encoding="utf-8")
        cls.javascript = (SITE_ROOT / "app.js").read_text(encoding="utf-8")
        cls.css = (SITE_ROOT / "styles.css").read_text(encoding="utf-8")
        cls.parser = StartTagCollector()
        cls.parser.feed(cls.html)

    def test_page_uses_local_assets_and_a_restrictive_csp(self) -> None:
        scripts = [attrs for tag, attrs in self.parser.tags if tag == "script"]
        stylesheets = [
            attrs
            for tag, attrs in self.parser.tags
            if tag == "link" and "stylesheet" in (attrs.get("rel") or "").split()
        ]
        csp_values = [
            attrs.get("content") or ""
            for tag, attrs in self.parser.tags
            if tag == "meta" and (attrs.get("http-equiv") or "").casefold() == "content-security-policy"
        ]

        self.assertEqual([item.get("src") for item in scripts], ["./app.js"])
        self.assertEqual([item.get("href") for item in stylesheets], ["./styles.css"])
        self.assertEqual(len(csp_values), 1)
        for directive in (
            "default-src 'self'",
            "connect-src 'self'",
            "object-src 'none'",
            "script-src 'self'",
            "style-src 'self'",
            "base-uri 'none'",
        ):
            self.assertIn(directive, csp_values[0])
        self.assertNotIn("'unsafe-inline'", csp_values[0])
        self.assertNotIn("'unsafe-eval'", csp_values[0])

    def test_page_has_no_embedded_active_content_or_inline_handlers(self) -> None:
        prohibited_tags = {"audio", "embed", "iframe", "object", "video"}
        for tag, attrs in self.parser.tags:
            self.assertNotIn(tag, prohibited_tags)
            self.assertFalse(any(name.casefold().startswith("on") for name in attrs))
        self.assertNotRegex(self.css, r"(?i)@import|url\s*\(")

    def test_untrusted_data_uses_text_only_dom_operations(self) -> None:
        for prohibited in (
            r"\.innerHTML\b",
            r"\.outerHTML\b",
            r"insertAdjacentHTML\s*\(",
            r"document\.write\s*\(",
            r"\beval\s*\(",
            r"new\s+Function\b",
        ):
            self.assertNotRegex(self.javascript, prohibited)
        self.assertIn(".textContent", self.javascript)
        self.assertIn('const DATA_URL = "./data/leaderboard.json";', self.javascript)
        self.assertEqual(len(re.findall(r"\bfetch\s*\(", self.javascript)), 1)
        self.assertIn("fetch(DATA_URL", self.javascript)
        self.assertNotRegex(self.javascript, r"(?i)https?://|//[a-z0-9.-]+/")

    def test_page_keeps_the_leaderboard_first_and_the_theme_accessible(self) -> None:
        self.assertLess(self.html.index('id="leaderboard"'), self.html.index('id="submit"'))
        self.assertIn("DON'T PANIC", self.html)
        self.assertIn("prefers-reduced-motion", self.css)
        self.assertIn("forced-colors", self.css)

        ids = [attrs["id"] for _, attrs in self.parser.tags if attrs.get("id")]
        self.assertEqual(len(ids), len(set(ids)))

    def test_committed_dataset_is_strict_and_counted(self) -> None:
        payload = json.loads((SITE_ROOT / "data" / "leaderboard.json").read_text(encoding="utf-8"))

        self.assertEqual(set(payload), {"schema_version", "entry_count", "entries"})
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["entry_count"], len(payload["entries"]))


if __name__ == "__main__":
    unittest.main()
