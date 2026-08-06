from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
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
        cls.javascript_sources = {
            path.relative_to(SITE_ROOT).as_posix(): path.read_text(encoding="utf-8")
            for path in sorted(SITE_ROOT.rglob("*.js"))
        }
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
        self.assertTrue(self.javascript_sources)
        for name, source in self.javascript_sources.items():
            for prohibited in (
                r"\.innerHTML\b",
                r"\.outerHTML\b",
                r"insertAdjacentHTML\s*\(",
                r"document\.write\s*\(",
                r"\beval\s*\(",
                r"new\s+Function\b",
            ):
                with self.subTest(source=name, prohibited=prohibited):
                    self.assertNotRegex(source, prohibited)
        self.assertIn(".textContent", self.javascript)
        self.assertIn('const DATA_URL = "./data/leaderboard.json";', self.javascript)
        self.assertEqual(len(re.findall(r"\bfetch\s*\(", self.javascript)), 1)
        self.assertNotRegex(self.javascript, r"(?i)https?://|//[a-z0-9.-]+/")

    def test_browser_uses_one_bounded_fetch_path_for_legacy_and_sharded_data(self) -> None:
        self.assertIn("async function fetchBoundedJson(", self.javascript)
        helper_start = self.javascript.index("async function fetchBoundedJson(")
        helper_end = self.javascript.index("\n}\n", helper_start + 1) + 2
        helper = self.javascript[helper_start:helper_end]
        self.assertIn("fetch(", helper)
        self.assertIn('cache: "no-cache"', helper)
        self.assertIn('credentials: "omit"', helper)
        self.assertIn('headers.get("content-length")', helper)
        self.assertIn("MAX_DATA_BYTES", helper)
        self.assertIn("response.arrayBuffer()", helper)
        self.assertIn("decodeStrictUtf8(bytes)", helper)
        self.assertIn("parseStrictJson(", helper)

        self.assertIn("fetchBoundedJson(DATA_URL)", self.javascript)
        self.assertGreaterEqual(self.javascript.count("fetchBoundedJson("), 3)
        self.assertRegex(
            self.javascript,
            r"hasExactKeys\(\s*[A-Za-z_$][A-Za-z0-9_$]*,\s*\[\s*\"index_version\",\s*"
            r"\"schema_version\",\s*\"entry_count\",\s*\"shard_count\",?\s*\]",
        )
        self.assertRegex(
            self.javascript,
            r"hasExactKeys\(\s*[A-Za-z_$][A-Za-z0-9_$]*,\s*\[\s*\"index_version\",\s*"
            r"\"schema_version\",\s*\"shard_id\",\s*\"entry_count\",\s*"
            r"\"entries\",?\s*\]",
        )
        self.assertRegex(self.javascript, r"\.padStart\(6,\s*\"0\"\)")
        self.assertIn('const SHARD_URL_PREFIX = "./data/leaderboard-";', self.javascript)
        self.assertIn('const SHARD_URL_SUFFIX = ".json";', self.javascript)
        self.assertRegex(
            self.javascript,
            r"SHARD_URL_PREFIX[^;\n]{0,160}SHARD_URL_SUFFIX",
        )
        self.assertRegex(
            self.javascript,
            r"isInteger\(\s*[A-Za-z_$][A-Za-z0-9_$]*\.shard_count,\s*0\s*\)",
        )
        self.assertRegex(
            self.javascript,
            r"\.shard_count\s*>\s*[A-Za-z_$][A-Za-z0-9_$]*\.entry_count",
        )
        self.assertNotRegex(
            self.javascript,
            r"(?i)(?:payload|index|descriptor)\.(?:url|path|href)\b",
        )

    def test_browser_fetches_time_out_and_shard_checks_stay_incremental(self) -> None:
        helper_start = self.javascript.index("async function fetchBoundedJson(")
        helper_end = self.javascript.index("\n}\n", helper_start + 1) + 2
        helper = self.javascript[helper_start:helper_end]
        for expected in (
            "DATA_FETCH_TIMEOUT_MS",
            "AbortController",
            "setTimeout(",
            "controller.abort()",
            "signal: controller.signal",
            "clearTimeout(",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, helper)

        load_start = self.javascript.index("async function loadNextShard(")
        load_end = self.javascript.index("\nfunction leaderboardUnavailable(", load_start)
        load_next_shard = self.javascript[load_start:load_end]
        self.assertIn("validateAndTrackShardRanking(", load_next_shard)
        self.assertNotIn("const combined", load_next_shard)
        self.assertNotIn("validateRanking(", load_next_shard)

        reset_start = self.javascript.index("function resetLeaderboardState(")
        reset_end = self.javascript.index("\n}\n", reset_start + 1) + 2
        reset = self.javascript[reset_start:reset_end]
        self.assertIn("createShardRankingState()", reset)
        self.assertGreaterEqual(self.javascript.count("resetLeaderboardState();"), 2)

    def test_shard_loading_state_enforces_cross_shard_boundaries(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is unavailable")
        completed = subprocess.run(
            [
                node,
                str(PROJECT_ROOT / "tests" / "js_leaderboard_loading_runner.js"),
                str(SITE_ROOT / "app.js"),
                str(SITE_ROOT / "data" / "leaderboard.json"),
            ],
            cwd=PROJECT_ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            json.loads(completed.stdout),
            {
                "bounded_timeout": True,
                "duplicate_rejected_without_mutation": True,
                "fetched_bom_rejected": True,
                "fetched_duplicate_rejected": True,
                "fetched_invalid_utf8_rejected": True,
                "fetched_valid_utf8_accepted": True,
                "first_rank_required": True,
                "fresh_state_accepts_previously_seen_id": True,
                "incremental_segments": True,
                "reversed_canonical_boundary_rejected": True,
                "wrong_rank_boundary_rejected": True,
            },
        )

    def test_unavailable_facet_latency_sorts_last(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is unavailable")
        completed = subprocess.run(
            [
                node,
                str(PROJECT_ROOT / "tests" / "js_sorting_runner.js"),
                str(SITE_ROOT / "app.js"),
            ],
            cwd=PROJECT_ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            json.loads(completed.stdout),
            {
                "latency_order": ["fast", "slow", "unavailable"],
                "half_up_scores": [6.3, 93.8],
            },
        )

    def test_paginated_controls_describe_the_loaded_result_scope(self) -> None:
        visible_text = re.sub(r"<[^>]+>", " ", self.html)
        visible_text = re.sub(r"\s+", " ", visible_text).casefold()
        for expected in (
            "search, hardware filters, and sorting apply only to results loaded so far",
            "find a loaded model",
            "loaded hardware",
            "sort loaded results by",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, visible_text)
        self.assertIn("No loaded results match these filters.", self.javascript)
        self.assertIn("load more results to expand the searchable set", self.javascript)

    def test_validity_is_first_class_and_defaults_to_clean_only(self) -> None:
        visible_text = re.sub(r"<[^>]+>", " ", self.html)
        visible_text = re.sub(r"\s+", " ", visible_text).casefold()
        for expected in (
            "clean only",
            "legacy: not reported",
            "measurement month",
            "validity",
            "as of",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, visible_text)
        self.assertRegex(
            self.html,
            r'<option\s+value="clean"\s+selected>Clean only</option>',
        )
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is unavailable")
        completed = subprocess.run(
            [
                node,
                str(PROJECT_ROOT / "tests" / "js_validity_filter_runner.js"),
                str(SITE_ROOT / "app.js"),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            json.loads(completed.stdout),
            {"clean_default": 1, "all": 4, "legacy": 1, "month": 2},
        )

    def test_evidence_bands_are_closed_validated_and_neutral(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is unavailable")
        completed = subprocess.run(
            [
                node,
                str(PROJECT_ROOT / "tests" / "js_evidence_bands_runner.js"),
                str(SITE_ROOT / "app.js"),
                str(SITE_ROOT / "data" / "leaderboard.json"),
            ],
            cwd=PROJECT_ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            json.loads(completed.stdout),
            {
                "wilson_five_of_five": {"lower_percent": 56, "upper_percent": 100},
                "wilson_zero_of_five": {"lower_percent": 0, "upper_percent": 44},
                "legacy_wilson_in_memory": {"lower_percent": 56, "upper_percent": 100},
                "legacy_score_text": "5/5 (56–100%)",
                "legacy_display_band_count": 1,
                "valid_projected_entry": True,
                "valid_projected_payload": True,
                "tampered_config_digest_rejected": True,
                "tampered_wilson_rejected": True,
                "corroboration_arithmetic_rejected": True,
                "distribution_order_rejected": True,
                "plausibility_basis_rejected": True,
                "signal_order_rejected": True,
                "caution_remains_valid": True,
                "caution_text_is_non_attesting": True,
                "parameter_scale_valid": True,
                "parameter_scale_precision_rejected": True,
                "parameter_scale_active_without_total_rejected": True,
                "parameter_scale_active_above_total_rejected": True,
                "transitive_rank_bands": True,
                "tampered_rank_band_rejected": True,
                "duplicate_config_cell_rejected": True,
                "names_do_not_change_bands": True,
                "partial_rank_bands_are_monotonic": True,
                "tampered_shard_rank_band_rejected": True,
                "delayed_shard_bridge_accepted": True,
                "neutral_default_tiebreak": True,
            },
        )

    def test_evidence_ui_uses_literal_non_attestation_language(self) -> None:
        visible_text = re.sub(r"<[^>]+>", " ", self.html)
        visible_text = re.sub(r"\s+", " ", visible_text).casefold()
        for expected in (
            "rank band",
            "95% wilson",
            "accepted content hashes, not people",
            "filters apply to that representative",
            "median/range",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, visible_text)
        for expected in (
            "Plausibility not evaluated; this is not verification.",
            "No plausibility flag; this is not verification.",
            "accepted hash",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, self.javascript)

    def test_browser_validators_accept_both_closed_transport_forms(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is unavailable")
        sources = sorted((SITE_ROOT / "data" / "submissions").glob("*.json"))
        self.assertGreaterEqual(len(sources), 2)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            submissions = root / "submissions"
            submissions.mkdir()
            for source in sources[:2]:
                shutil.copyfile(source, submissions / source.name)
            legacy = root / "leaderboard.json"
            built = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "scripts" / "build_leaderboard.py"),
                    "--submissions-dir",
                    str(submissions),
                    "--output",
                    str(legacy),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(built.returncode, 0, built.stderr)
            completed = subprocess.run(
                [
                    node,
                    str(PROJECT_ROOT / "tests" / "js_leaderboard_transport_runner.js"),
                    str(SITE_ROOT / "app.js"),
                    str(legacy),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            json.loads(completed.stdout),
            {
                "legacy": True,
                "index": True,
                "index_extra_key": False,
                "index_nonzero_entries_zero_shards": False,
                "index_more_shards_than_entries": False,
                "shard": True,
                "shard_extra_key": False,
                "shard_wrong_id": False,
                "legacy_reordered_tie": False,
            },
        )

    def test_page_keeps_the_leaderboard_first_and_the_theme_accessible(self) -> None:
        self.assertLess(self.html.index('id="leaderboard"'), self.html.index('id="submit"'))
        self.assertIn("DON'T PANIC", self.html)
        self.assertIn("prefers-reduced-motion", self.css)
        self.assertIn("forced-colors", self.css)

        ids = [attrs["id"] for _, attrs in self.parser.tags if attrs.get("id")]
        self.assertEqual(len(ids), len(set(ids)))

    def test_model_validator_mirrors_descriptor_hardening(self) -> None:
        limits = {
            "display_name": ("MODEL_DISPLAY_NAME_MAX", 160),
            "source": ("MODEL_SOURCE_MAX", 240),
            "precision": ("MODEL_PRECISION_MAX", 80),
        }
        for field, (constant, maximum) in limits.items():
            with self.subTest(field=field, contract="maximum"):
                self.assertRegex(
                    self.javascript,
                    rf"\bconst\s+{constant}\s*=\s*{maximum}\s*;",
                )

        validate_model_start = self.javascript.index("function validateModel(")
        validate_model_end = self.javascript.index(
            "\nfunction validateHardware(",
            validate_model_start,
        )
        validate_model = self.javascript[validate_model_start:validate_model_end]
        helper_match = re.search(
            r"(?P<helper>[A-Za-z_$][A-Za-z0-9_$]*)\(\s*model\.display_name\s*,"
            r"\s*MODEL_DISPLAY_NAME_MAX\s*\)",
            validate_model,
        )
        self.assertIsNotNone(helper_match)
        helper = helper_match.group("helper")
        for field, (constant, _) in limits.items():
            with self.subTest(field=field, contract="validator"):
                self.assertRegex(
                    validate_model,
                    rf"{re.escape(helper)}\(\s*model\.{field}\s*,\s*{constant}\s*\)",
                )

        helper_start = self.javascript.index(f"function {helper}(")
        helper_end = self.javascript.index("\nfunction ", helper_start + 1)
        helper_source = self.javascript[helper_start:helper_end]
        self.assertIn("isPublicDescriptorText(", helper_source)
        self.assertRegex(self.javascript, r"\\x20-\\x7e")

        lowered = self.javascript.casefold()
        for required_pattern in (
            "ignore",
            "disregard",
            "override",
            "bypass",
            "forget",
            "accept",
            "system",
            "instructions",
            "prompt",
            "assistant",
            "developer",
            "reviewer",
            "maintainer",
            "codex",
            "coderabbit",
            "mark",
            "safe",
            "```",
            "script",
            "<!--",
        ):
            with self.subTest(required_pattern=required_pattern):
                self.assertIn(required_pattern, lowered)
        self.assertIn("@", lowered)
        self.assertIn(r"\s*:", lowered)

    def test_public_chrome_distinguishes_integrity_from_provenance(self) -> None:
        visible_text = re.sub(r"<[^>]+>", " ", self.html)
        visible_text = re.sub(r"\s+", " ", visible_text).casefold()

        self.assertRegex(
            visible_text,
            r"self-reported.{0,60}unverified",
        )
        self.assertRegex(
            visible_text,
            r"hash(?:es)?\b.{0,80}\bintegrity\b.{0,80}\bnot\b.{0,40}\bprovenance\b",
        )

    def test_committed_transport_accepts_only_a_closed_monolith_or_index(self) -> None:
        payload = json.loads((SITE_ROOT / "data" / "leaderboard.json").read_text(encoding="utf-8"))

        self.assertEqual(payload["schema_version"], "1.0")
        if "entries" in payload:
            self.assertEqual(set(payload), {"schema_version", "entry_count", "entries"})
            self.assertEqual(payload["entry_count"], len(payload["entries"]))
        else:
            self.assertEqual(
                set(payload),
                {"index_version", "schema_version", "entry_count", "shard_count"},
            )
            self.assertEqual(payload["index_version"], "1.0")
            self.assertEqual(payload["entry_count"] == 0, payload["shard_count"] == 0)
            self.assertLessEqual(payload["shard_count"], payload["entry_count"])


if __name__ == "__main__":
    unittest.main()
