# PR Draft: fix/sqlalchemy-orm-declarative-import → odysseus-dev/odysseus:dev

**Branch:** `fix/sqlalchemy-orm-declarative-import`
**Fork issue:** [#163](https://github.com/jdmanring/odysseus/issues/163) (open)
**Status:** Single clean commit. File upstream issue first, fill in `Fixes #___`, then open PR.
**Context:** Sibling to `#51` (utcnow deprecation) — same class of SQLAlchemy-family deprecation cleanup.

---

## Upstream PR title

`fix(db): import declarative_base/declared_attr from sqlalchemy.orm`

---

## Summary

### Problem

`core/database.py` imports the declarative helpers from the legacy
`sqlalchemy.ext.declarative` location:

```python
from sqlalchemy.ext.declarative import declarative_base, declared_attr
```

On SQLAlchemy 2.0 this emits a `MovedIn20Warning` on every import of
`core.database` (which the whole app imports early):

```
MovedIn20Warning: The declarative_base() function is now available as
sqlalchemy.orm.declarative_base(). (deprecated since: 2.0)
```

### Fix

Both names are re-exported from `sqlalchemy.orm` (verified on 2.0.50), which the
file already imports from — so fold them into that line and drop the deprecated
import:

```python
# Before
from sqlalchemy.ext.declarative import declarative_base, declared_attr
from sqlalchemy.orm import relationship, sessionmaker, backref

# After
from sqlalchemy.orm import declarative_base, declared_attr, relationship, sessionmaker, backref
```

No behavior change — same objects, current import path, warning gone. Verified
with `python -W error::DeprecationWarning -c "import core.database"` (clean).

### Scope

One file changed: `core/database.py` (−1 line: two imports folded into one).
Plus a source-assertion regression guard,
`tests/test_database_declarative_import.py`, so the import cannot drift back to
the deprecated location.
