# PR Draft: feat/logging-audit → pewdiepie-archdaemon/odysseus:dev

**Branch:** `jdmanring/odysseus:feat/logging-audit`
**Base:** `jdmanring/odysseus:feat/logging-core` (depends on PR #1)
**Upstream Issues Addressed:**
- [#3803](https://github.com/pewdiepie-archdaemon/odysseus/issues/3803) — "No audit trail for sensitive operations (auth events, vault unlock, admin wipes)"
- [#3799](https://github.com/pewdiepie-archdaemon/odysseus/issues/3799) — "audit logging for sensitive operations" in scope
**Status:** Ready to file after feat/logging-core merges

---

## Title

`feat(logging): audit trail for auth events and settings changes`

---

## Description

### Problem

The upstream hardening audit (#3803) explicitly identified "No audit trail for
sensitive operations (auth events, vault unlock, admin wipes)" as a finding.
Currently, when an admin creates or deletes a user, changes a password, or
modifies a critical setting, there is no record of who did it or when. This
is a security gap for any multi-user deployment.

### Solution

Add structured audit logging for all authentication and authorization events,
plus settings changes. Each event includes the actor (who), the action (what),
and the outcome (success/failure).

**Auth events logged:**
- `auth_login_success` / `auth_login_failed` (with reason: invalid_password, invalid_totp)
- `auth_signup`
- `auth_logout`
- `auth_password_changed` / `auth_password_change_failed`
- `auth_admin_create_user` / `auth_admin_delete_user`

**Settings audit:**
- Every `POST /api/auth/settings` request logs the actor, the key changed,
  and the old → new values

All events use structured keys so they're filterable with `jq`:
```bash
# Find all failed login attempts
jq 'select(.event == "auth_login_failed")' data/logs/odysseus.log

# Find all settings changes by a specific admin
jq 'select(.event == "settings_changed" and .admin == "alice")' data/logs/odysseus.log
```

### Long-term Benefits

1. **Security incident response:** When something goes wrong — a user was
   deleted, a password was reset, a critical setting was changed — the audit
   log provides the forensic evidence to understand what happened and who
   did it.

2. **Compliance:** Many organizations require audit trails for administrative
   actions. This provides the basic infrastructure for compliance without
   requiring a separate audit system.

3. **Accountability:** In multi-user deployments, the audit log ensures that
   administrators can be held accountable for their actions. Every user
   management operation is attributed to a specific user.

4. **Debugging:** When a setting was accidentally changed and caused an issue,
   the audit log shows exactly when and by whom, making it easy to roll back.

### Files Changed

- `routes/auth_routes.py` — auth event logging + settings change audit

### Testing

- [x] All existing tests pass (64 tests on base branch)
- [ ] Verify auth events appear in log output after login/logout/signup
- [ ] Verify settings changes appear in log output with old/new values

---

## Filing Notes

This PR depends on `feat/logging-core` and should be filed after it merges.
It targets `dev`. The changes are small (one file) but the security impact
is significant — this directly addresses a finding from the upstream
hardening audit (#3803).
