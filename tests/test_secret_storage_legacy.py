"""Behavioral: secret_storage encrypt/decrypt, incl. legacy unprefixed tokens.

Regression: an HF token was stored as a raw Fernet ciphertext with no `enc:`
prefix. decrypt() treated the missing prefix as "legacy plaintext" and returned
the ciphertext unchanged, so the app sent a 140-char blob as the token and every
authenticated HF call silently failed while the UI's bool() auth pill still
showed "configured". decrypt() now self-repairs an unprefixed Fernet value.
"""
from src.secret_storage import encrypt, decrypt, _get_fernet, _PREFIX


def test_prefixed_round_trip():
    e = encrypt("hf_realtoken123")
    assert e.startswith(_PREFIX)
    assert decrypt(e) == "hf_realtoken123"


def test_legacy_unprefixed_fernet_self_repairs():
    # Simulate the bad on-disk value: a Fernet ciphertext with no enc: prefix.
    raw = _get_fernet().encrypt(b"hf_legacytoken").decode("ascii")
    assert not raw.startswith(_PREFIX)
    assert decrypt(raw) == "hf_legacytoken"


def test_genuine_plaintext_passes_through():
    # A real legacy-plaintext secret is not a valid Fernet token and must not be
    # mangled by the self-repair path.
    assert decrypt("plainpassword") == "plainpassword"


def test_empty_is_empty():
    assert decrypt("") == ""
    assert encrypt("") == ""


def test_encrypt_is_idempotent_on_prefixed():
    e = encrypt("secret")
    assert encrypt(e) == e
