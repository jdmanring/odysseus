"""Unit tests for the fork's upstream ingest pipeline (fork-only tooling).

Covers the two defects the 2026-07-19 sync exposed:
- Gate subprocesses inherited a color-capable terminal env; Python 3.14's
  colorized argparse help injected ANSI escapes into --help output and broke
  upstream's plain-substring test asserts.
- The docs/ media cleanup only removed files with an assets/ counterpart, so a
  merge-added orphan image (docs/odysseus-browser.jpg) survived to fail
  upstream's test_docs_no_orphan_images in Gate 3.
"""
import importlib.util
import os
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
PIPELINE = REPO / "tooling" / "sync-upstreams" / "upstream_ingest_pipeline.py"

_spec = importlib.util.spec_from_file_location("upstream_ingest_pipeline", PIPELINE)
pipeline = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pipeline)


class TestGateEnv:
    def test_disables_all_color_channels(self):
        hostile = {
            "COLORTERM": "truecolor",
            "FORCE_COLOR": "1",
            "CLICOLOR_FORCE": "1",
            "CLICOLOR": "1",
            "PATH": "/usr/bin",
        }
        with mock.patch.dict(os.environ, hostile, clear=True):
            env = pipeline._gate_env()
        assert env["NO_COLOR"] == "1"
        assert env["PYTHON_COLORS"] == "0"
        for var in ("COLORTERM", "FORCE_COLOR", "CLICOLOR_FORCE", "CLICOLOR"):
            assert var not in env
        assert env["PATH"] == "/usr/bin", "must not drop unrelated variables"

    def test_pins_terminal_width(self):
        # argparse wraps help text to COLUMNS; an unusual width changes line
        # breaks and can break substring asserts just like color codes do.
        with mock.patch.dict(os.environ, {"COLUMNS": "213"}, clear=True):
            assert pipeline._gate_env()["COLUMNS"] == "80"

    def test_all_three_gates_use_the_env(self):
        src = PIPELINE.read_text(encoding="utf-8")
        gatekeeper = src[src.index("class GateKeeper") : src.index("class PromotionEngine")]
        assert gatekeeper.count("env=self._env") == 3, (
            "every gate subprocess must run under the deterministic env"
        )


class TestClassifyDocsMedia:
    def test_moved_to_assets_duplicate_is_removed(self):
        out = pipeline._classify_docs_media(
            ["docs/hero.png"], {"hero.png"}, lambda name: True
        )
        assert out == [("docs/hero.png", "moved-to-assets")]

    def test_unreferenced_orphan_is_removed(self):
        # The 2026-07-19 failure shape: upstream adds docs/odysseus-browser.jpg,
        # references it only in their README — which the fork PROTECTS and
        # restores, leaving the image unreferenced.
        out = pipeline._classify_docs_media(
            ["docs/odysseus-browser.jpg"], set(), lambda name: False
        )
        assert out == [("docs/odysseus-browser.jpg", "orphan")]

    def test_referenced_new_media_is_kept(self):
        out = pipeline._classify_docs_media(
            ["docs/new-feature.gif"], set(), lambda name: True
        )
        assert out == []

    def test_assets_match_is_by_basename_not_path(self):
        out = pipeline._classify_docs_media(
            ["docs/sub/hero.png"], {"hero.png"}, lambda name: True
        )
        assert out == [("docs/sub/hero.png", "moved-to-assets")]


class TestPushHelpText:
    def test_push_help_does_not_promise_pushing_the_mirror(self):
        # The code deliberately never pushes upstream-mirror (GITHUB_TOKEN
        # cannot push upstream workflow files); the help text used to claim
        # otherwise.
        src = PIPELINE.read_text(encoding="utf-8")
        help_line = next(
            line for line in src.splitlines()
            if 'help="Push integration' in line
        )
        assert "upstream-mirror is never pushed" in help_line
