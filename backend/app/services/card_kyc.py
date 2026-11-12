"""Identity data required by our Online card flow."""
import re


def normalize_contacts(email, phone):
    email = (email or "").strip()
    phone = re.sub(r"[\s()-]", "", phone or "")
    domain = email.rsplit("@", 1)[-1].lower()
    if (not re.fullmatch(r"[^@\s]+@(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,63}", email)
            or domain in ("example.com", "example.org", "example.net")
            or domain.endswith((".test", ".invalid", ".example"))):
        raise ValueError("Укажите действующий email.")
    if not re.fullmatch(r"\+[1-9]\d{6,14}", phone):
        raise ValueError("Укажите телефон с кодом страны, например +7 999 123-45-67.")
    return email, phone


def contacts_ready(user):
    try:
        normalize_contacts(getattr(user, "email", None), getattr(user, "phone", None))
        return True
    except ValueError:
        return False


def kyc_ready(user):
    return bool(user.kyc_status == "success" and user.kyc_first_name and user.kyc_last_name
                and user.kyc_birth_date and user.kyc_passport)
