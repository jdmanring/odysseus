"""Integration tests for the logging system.

Verifies that:
1. structlog is configured and produces structured output
2. Sensitive data redaction works in practice
3. JSON file output is valid JSON lines
4. Debug mode and subsystem filtering work
5. Contextvars are injected into log events
"""

import json
import logging
import os
import subprocess
import sys

import pytest


@pytest.fixture(autouse=True)
def _reset_logging():
    """Reset logging state before each test."""
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.WARNING)
    yield
    root.handlers.clear()
    root.setLevel(logging.WARNING)


class TestEndToEndLogging:
    """Run Python code in a subprocess to verify logging behavior."""

    def _run(self, code: str, env_overrides: dict = None) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if not k.startswith("ODYSSEUS_")}
        if env_overrides:
            env.update(env_overrides)
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env["PYTHONPATH"] = repo_root + os.pathsep + env.get("PYTHONPATH", "")
        return subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, env=env, cwd=repo_root,
        )

    def test_structlog_produces_json_with_request_id(self, tmp_path):
        """Verify that a logger call produces structured JSON with expected keys."""
        log_file = str(tmp_path / "test.log")
        result = self._run(
            "import structlog\n"
            "from src.logging_config import setup_logging\n"
            "setup_logging()\n"
            "logger = structlog.get_logger('test')\n"
            "logger.info('test_event', key='value')\n"
            "import time; time.sleep(0.1)\n"
            "print('done')",
            {"ODYSSEUS_LOG_FILE": log_file},
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert os.path.exists(log_file)
        with open(log_file) as f:
            lines = f.readlines()
        assert len(lines) >= 1
        entry = json.loads(lines[-1].strip())
        assert entry["event"] == "test_event"
        assert entry["key"] == "value"
        assert "level" in entry
        assert "logger" in entry
        assert "timestamp" in entry

    def test_redaction_in_json_output(self, tmp_path):
        """Verify that sensitive keys are redacted in JSON log output."""
        log_file = str(tmp_path / "test.log")
        result = self._run(
            "import structlog\n"
            "from src.logging_config import setup_logging\n"
            "setup_logging()\n"
            "logger = structlog.get_logger('test')\n"
            "logger.info('login_attempt', password='secret123', username='alice')\n"
            "import time; time.sleep(0.1)\n"
            "print('done')",
            {"ODYSSEUS_LOG_FILE": log_file},
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        with open(log_file) as f:
            content = f.read()
        assert "<REDACTED>" in content
        assert "secret123" not in content
        assert "alice" in content  # username is not sensitive

    def test_debug_mode_via_env(self, tmp_path):
        """Verify ODYSSEUS_DEBUG=1 sets DEBUG level."""
        log_file = str(tmp_path / "debug.log")
        result = self._run(
            "import logging\n"
            "from src.logging_config import setup_logging\n"
            "setup_logging()\n"
            "print(logging.getLogger().level)",
            {"ODYSSEUS_LOG_FILE": log_file, "ODYSSEUS_DEBUG": "1"},
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert result.stdout.strip() == "10"  # DEBUG=10

    def test_normal_mode_is_info(self, tmp_path):
        """Verify default mode sets INFO level."""
        log_file = str(tmp_path / "info.log")
        result = self._run(
            "import logging\n"
            "from src.logging_config import setup_logging\n"
            "setup_logging()\n"
            "print(logging.getLogger().level)",
            {"ODYSSEUS_LOG_FILE": log_file},
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert result.stdout.strip() == "20"  # INFO=20

    def test_subsystem_debug_filtering(self, tmp_path):
        """Verify ODYSSEUS_DEBUG_SUBSYSTEMS enables DEBUG for specific loggers."""
        log_file = str(tmp_path / "subsystem.log")
        code = (
            "import logging\n"
            "from src.logging_config import setup_logging\n"
            "setup_logging()\n"
            "root = logging.getLogger()\n"
            "llm = logging.getLogger('odysseus.src.llm_core')\n"
            "other = logging.getLogger('odysseus.routes.chat')\n"
            "print('root=%d llm=%d other=%d' % (root.level, llm.level, other.level))"
        )
        result = self._run(code, {
            "ODYSSEUS_LOG_FILE": log_file,
            "ODYSSEUS_DEBUG": "1",
            "ODYSSEUS_DEBUG_SUBSYSTEMS": "odysseus.src.llm_core",
        })
        assert result.returncode == 0, f"stderr: {result.stderr}"
        output = result.stdout.strip()
        assert "root=10" in output   # DEBUG
        assert "llm=10" in output    # DEBUG (matched subsystem)
        # other is NOTSET (0) — it inherits from root which is DEBUG
        assert "other=0" in output

    def test_contextvars_in_log_output(self, tmp_path):
        """Verify that contextvars are injected into log events."""
        log_file = str(tmp_path / "ctx.log")
        code = (
            "import structlog\n"
            "from src.logging_config import setup_logging\n"
            "from src.log_context import bind_request_context, clear_request_context\n"
            "setup_logging()\n"
            "bind_request_context(request_id='test-req-123', user_id='user-456')\n"
            "logger = structlog.get_logger('test')\n"
            "logger.info('ctx_test')\n"
            "clear_request_context()\n"
            "import time; time.sleep(0.1)\n"
            "print('done')"
        )
        result = self._run(code, {"ODYSSEUS_LOG_FILE": log_file})
        assert result.returncode == 0, f"stderr: {result.stderr}"
        with open(log_file) as f:
            lines = f.readlines()
        entry = json.loads(lines[-1].strip())
        assert entry["event"] == "ctx_test"
        assert entry["request_id"] == "test-req-123"
        assert entry["user_id"] == "user-456"

    def test_json_output_is_valid_jsonl(self, tmp_path):
        """Verify that each line in the log file is valid JSON."""
        log_file = str(tmp_path / "jsonl.log")
        code = (
            "import structlog\n"
            "from src.logging_config import setup_logging\n"
            "setup_logging()\n"
            "logger = structlog.get_logger('test')\n"
            "for i in range(5):\n"
            "    logger.info('batch_event', index=i)\n"
            "import time; time.sleep(0.05)\n"
            "print('done')"
        )
        result = self._run(code, {"ODYSSEUS_LOG_FILE": log_file})
        assert result.returncode == 0, f"stderr: {result.stderr}"
        with open(log_file) as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
        assert len(lines) >= 5
        for line in lines:
            entry = json.loads(line)  # Should not raise
            assert "event" in entry
            assert "timestamp" in entry
