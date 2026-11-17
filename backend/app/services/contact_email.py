"""Canonical email formatting shared by contact storage and provider requests."""
import re

EMAIL_PATTERN = re.compile(r"[^@\s]+@(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,63}")


def normalize_email(value: str | None) -> str:
    email = re.sub(r"[\s\u200b-\u200d\ufeff]+", "", value or "")
    local, separator, domain = email.rpartition("@")
    return f"{local}@{domain.lower()}" if separator else domain


def valid_email(value: str) -> bool:
    return bool(EMAIL_PATTERN.fullmatch(value))
