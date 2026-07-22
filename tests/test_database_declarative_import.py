"""Guard: core/database.py must import declarative_base/declared_attr from the
current sqlalchemy.orm location, not the deprecated sqlalchemy.ext.declarative
(which emits MovedIn20Warning on SQLAlchemy 2.0). See #163."""

import re
from pathlib import Path


SRC = Path(__file__).resolve().parent.parent / "core/database.py"


def test_no_deprecated_ext_declarative_import():
    text = SRC.read_text(encoding="utf-8")
    assert "from sqlalchemy.ext.declarative import" not in text


def test_declarative_names_come_from_orm():
    text = SRC.read_text(encoding="utf-8")
    orm_names = ",".join(re.findall(r"from sqlalchemy\.orm import ([^\n]+)", text))
    assert "declarative_base" in orm_names
    assert "declared_attr" in orm_names
