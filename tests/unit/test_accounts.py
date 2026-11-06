"""The account rules: names, secrets, hashing and the limit on wrong guesses."""

from __future__ import annotations

import pytest

from marketlab import accounts as a


@pytest.mark.parametrize("name", ["shi", "Shivam_D", "abc", "a" * 20, "x1_2"])
def test_good_usernames(name: str) -> None:
    assert a.check_username(name) is None


@pytest.mark.parametrize(
    "name", ["ab", "a" * 21, "has space", "dash-name", "guest-ab12cd", "né", "", "admin", "Root", "f_u_c_k99"]
)
def test_bad_usernames(name: str) -> None:
    assert a.check_username(name) is not None


def test_a_guest_name_can_never_be_a_username() -> None:
    assert a.check_username(a.new_guest_name()) is not None  # the hyphen is not allowed in a username


@pytest.mark.parametrize("secret", ["red4242", "purple4217", "Blue-Otter 9", "tiger7777"])
def test_good_secrets(secret: str) -> None:
    assert a.check_secret(secret, "someone") is None


def test_five_characters_is_one_short() -> None:
    assert a.check_secret("red42", "x") is not None  # the form's example is 'red4242' for this reason


@pytest.mark.parametrize("secret", ["12345678", "abc", "password", "Password1", "x" * 65, "SHIVAM_D"])
def test_weak_secrets_are_refused(secret: str) -> None:
    assert a.check_secret(secret, "shivam_d") is not None


def test_a_stored_secret_is_a_salted_hash_and_checks_out() -> None:
    first, second = a.hash_secret("purple4217"), a.hash_secret("purple4217")
    assert first != second  # a fresh salt each time
    assert "purple" not in first
    assert a.verify_secret("purple4217", first)
    assert a.verify_secret("  PURPLE4217 ", first)  # capitals and end spaces do not matter
    assert not a.verify_secret("purple4218", first)
    assert not a.verify_secret("purple4217", "garbage")


def test_tokens_are_kept_only_as_hashes() -> None:
    token = a.new_token()
    assert a.token_hash(token) != token and len(a.token_hash(token)) == 64
    assert a.new_token() != token


def test_the_rate_limit_blocks_then_lets_go() -> None:
    now = [0.0]
    limit = a.RateLimit(3, 60, lambda: now[0])
    assert limit.wait("k") == 0
    for _ in range(3):
        limit.hit("k")
    assert 0 < limit.wait("k") <= 61
    assert limit.wait("other") == 0
    now[0] = 61
    assert limit.wait("k") == 0
    limit.hit("k")
    limit.clear("k")
    assert limit.wait("k") == 0
