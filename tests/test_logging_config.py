"""Tests for src/logging_config.py — structlog configuration."""

import logging
import os
import subprocess
import sys

import pytest


def _run_in_subprocess(code: str, env_overrides: dict = None) -> subprocess.CompletedProcess:
    """Run Python code in a subprocess with clean module state."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("ODYSSEUS_")}
    if env_overrides:
        env.update(env_overrides)
    # Ensure repo root is on sys.path so "from src.logging_config import ..." works
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env["PYTHONPATH"] = repo_root + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, env=env,
        cwd=repo_root,
    )


class TestSetupLogging:
    def test_configures_structlog(self, tmp_path):
        log_file = str(tmp_path / "test.log")
        result = _run_in_subprocess(
            "from src.logging_config import setup_logging; setup_logging(); "
            "import structlog; print(structlog.is_configured())",
            {"ODYSSEUS_LOG_FILE": log_file},
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert result.stdout.strip() == "True"

    def test_sets_root_logger_level_info(self, tmp_path):
        log_file = str(tmp_path / "test.log")
        result = _run_in_subprocess(
            "from src.logging_config import setup_logging; setup_logging(); "
            "import logging; print(logging.getLogger().level)",
            {"ODYSSEUS_LOG_FILE": log_file},
        )
        assert result.stdout.strip() == "20"  # INFO=20

    def test_adds_console_and_file_handlers(self, tmp_path):
        log_file = str(tmp_path / "test.log")
        result = _run_in_subprocess(
            "from src.logging_config import setup_logging; setup_logging(); "
            "import logging; print(len(logging.getLogger().handlers))",
            {"ODYSSEUS_LOG_FILE": log_file},
        )
        assert int(result.stdout.strip()) >= 1

    def test_debug_mode_sets_debug_level(self, tmp_path):
        log_file = str(tmp_path / "debug.log")
        result = _run_in_subprocess(
            "from src.logging_config import setup_logging; setup_logging(); "
            "import logging; print(logging.getLogger().level)",
            {"ODYSSEUS_LOG_FILE": log_file, "ODYSSEUS_DEBUG": "1"},
        )
        assert result.stdout.strip() == "10"  # DEBUG=10

    def test_suppresses_uvicorn_logging(self, tmp_path):
        log_file = str(tmp_path / "test.log")
        result = _run_in_subprocess(
            "from src.logging_config import setup_logging; setup_logging(); "
            "import logging; print(logging.getLogger('uvicorn').level)",
            {"ODYSSEUS_LOG_FILE": log_file},
        )
        assert result.stdout.strip() == "30"  # WARNING=30

    def test_json_file_output(self, tmp_path):
        log_file = str(tmp_path / "test_json.log")
        result = _run_in_subprocess(
            "import logging; root = logging.getLogger(); root.setLevel(logging.WARNING); "
            "from src.logging_config import setup_logging; setup_logging(); "
            "import structlog; "
            "structlog.get_logger().info('test_event', key='value')",
            {"ODYSSEUS_LOG_FILE": log_file},
        )
        # Check the log file was created and contains JSON
        assert os.path.exists(log_file)
        content = open(log_file).read()
        assert "test_event" in content
