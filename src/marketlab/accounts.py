"""Accounts: who may use a practice account. Rules, secrets and rate limits, with no web code in here.

There is no email and no real name. A person picks a username and a *secret*: a favourite word and a number,
like ``red42``. That is a password under a friendlier name, so it is treated like one: never stored, only a slow
salted hash of it (scrypt, built into Python), and wrong guesses are limited. Nothing real is protected here, which
is why this is kept small. If someone forgets their secret the account cannot be recovered. That is stated on the
sign-in page.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from collections import deque
from collections.abc import Callable

USERNAME = re.compile(r"[A-Za-z0-9_]{3,20}")
SECRET_MIN, SECRET_MAX = 6, 64
GUEST_PREFIX = "guest-"  # a hyphen is not allowed in a username, so a guest name can never be taken by a person

# Names that look official, or that we would not want shown in a standings table. A short list, not a filter that
# catches everything: it also stops innocent names that contain a listed word, which is the price of keeping it simple.
RESERVED = frozenset({"admin", "administrator", "root", "system", "support", "moderator", "claude", "anthropic", "you"})
BLOCKED_PARTS = ("fuck", "shit", "bitch", "cunt", "asshole", "nazi", "hitler", "porn", "rapist")

# The secrets people reach for first. Checked after lower-casing.
COMMON_SECRETS = frozenset(
    {
        "password", "password1", "passw0rd", "qwerty", "qwerty1", "qwerty123", "letmein", "iloveyou", "welcome",
        "admin123", "abc123", "monkey", "dragon", "football", "cricket", "sachin10", "red1", "red12", "red123",
        "blue1", "blue12", "blue123", "love1", "love12", "love123", "secret", "secret1", "secret123",
    }
)  # fmt: skip


def check_username(name: str) -> str | None:
    """Why this username cannot be used, or None if it can."""
    if not USERNAME.fullmatch(name):
        return "A username is 3 to 20 letters, numbers or underscores."
    plain = re.sub(r"[\d_]", "", name.lower())
    if name.lower() in RESERVED or any(word in plain for word in BLOCKED_PARTS):
        return "Please pick a different username."
    return None


def normalise_secret(secret: str) -> str:
    """Secrets ignore capital letters and spaces at the ends, so 'Red42 ' and 'red42' are the same secret."""
    return secret.strip().casefold()


def check_secret(secret: str, username: str) -> str | None:
    """Why this secret is too weak to accept for a new account, or None if it is fine."""
    plain = normalise_secret(secret)
    if len(plain) < SECRET_MIN:
        return f"Use at least {SECRET_MIN} characters, for example a favourite word and a number like purple4217."
    if len(plain) > SECRET_MAX:
        return f"Use at most {SECRET_MAX} characters."
    if plain.isdigit():
        return "Numbers alone are too easy to guess. Add a word, like purple42."
    if plain in COMMON_SECRETS or plain == username.casefold():
        return "That one is too common. Try a less obvious word and number."
    return None


# -- storing a secret ------------------------------------------------------------------------------------------

_N, _R, _P = 2**14, 8, 1  # scrypt cost: about 50 ms on a laptop, slow enough to make mass guessing expensive


def hash_secret(secret: str) -> str:
    """A salted, slow hash to store instead of the secret: 'scrypt$salt$hash' (the cost is fixed in this file)."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(normalise_secret(secret).encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_secret(secret: str, stored: str) -> bool:
    try:
        kind, salt_hex, digest_hex = stored.split("$")
        if kind != "scrypt":
            return False
        digest = hashlib.scrypt(
            normalise_secret(secret).encode(), salt=bytes.fromhex(salt_hex), n=_N, r=_R, p=_P, dklen=32
        )
    except ValueError:
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


# -- login tokens ----------------------------------------------------------------------------------------------


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    """What the database keeps of a token: a leaked database file then cannot be used to sign in."""
    return hashlib.sha256(token.encode()).hexdigest()


def new_guest_name() -> str:
    return GUEST_PREFIX + secrets.token_hex(3)


# -- slowing down guessing -------------------------------------------------------------------------------------


class RateLimit:
    """At most `limit` events per key in any `window` seconds. Kept in memory, so it is per server process."""

    def __init__(self, limit: int, window: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.limit = limit
        self.window = window
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    def _recent(self, key: str) -> deque[float]:
        hits = self._hits.get(key)
        if hits is None:
            return deque()
        cutoff = self._clock() - self.window
        while hits and hits[0] <= cutoff:
            hits.popleft()
        if not hits:
            del self._hits[key]
        return hits

    def wait(self, key: str) -> int:
        """Seconds until this key may try again; 0 if it may try now."""
        hits = self._recent(key)
        if len(hits) < self.limit:
            return 0
        return max(1, int(hits[0] + self.window - self._clock()) + 1)

    def hit(self, key: str) -> None:
        self._recent(key)
        self._hits.setdefault(key, deque()).append(self._clock())

    def clear(self, key: str) -> None:
        self._hits.pop(key, None)
