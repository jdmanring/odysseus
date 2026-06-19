"""Regression tests for ApiToken.last_used_at utcnow deprecation fix.

app.py's _touch_last_used() previously called datetime.utcnow(), which is
deprecated since Python 3.12. The fix imports and uses utcnow_naive() from
core.database instead — consistent with every other timestamp in the codebase.

These tests verify:
1. app.py imports utcnow_naive from core.database
2. app.py does not call datetime.utcnow() anywhere
3. The utcnow_naive() function returns a naive UTC datetime (no tzinfo)
"""

import ast
import inspect
from pathlib import Path

import pytest


APP_PY = Path(__file__).parent.parent / "app.py"


def _parse_app():
    return ast.parse(APP_PY.read_text())


def test_app_imports_utcnow_naive():
    """app.py must import utcnow_naive from core.database."""
    tree = _parse_app()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "core.database":
                names = {alias.name for alias in node.names}
                if "utcnow_naive" in names:
                    return
    pytest.fail("app.py does not import utcnow_naive from core.database")


def test_app_does_not_call_datetime_utcnow():
    """app.py must not call datetime.utcnow() — it is deprecated in Python 3.12+."""
    source = APP_PY.read_text()
    assert "datetime.utcnow()" not in source, (
        "app.py calls deprecated datetime.utcnow(). "
        "Use utcnow_naive() from core.database instead."
    )


def test_utcnow_naive_returns_naive_datetime():
    """utcnow_naive() must return a naive datetime (tzinfo is None)."""
    from core.database import utcnow_naive

    result = utcnow_naive()
    assert result.tzinfo is None, (
        "utcnow_naive() must return a naive datetime for SQLAlchemy DateTime columns"
    )
