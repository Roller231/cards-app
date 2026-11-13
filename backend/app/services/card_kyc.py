"""Identity data required by our Online card flow."""
import calendar
import random
import re
from datetime import date


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


# ---------------------------------------------------------------------------
# Synthetic identity for crypto-paid Online cards
# ---------------------------------------------------------------------------
# O-Plata's partner/start only needs well-formed identity fields (real-looking
# name, valid phone, non-example email); per provider confirmation the passport
# document itself is not verified on this flow. Crypto-paid Online issuance
# therefore generates a stable synthetic identity per user. Real NeuroVision
# KYC always wins: it overwrites these fields and the session marker, after
# which every flow (SBP, balance, crypto) uses the real data.

SYNTHETIC_KYC_SESSION = "synthetic"

_MALE_FIRST = [
    "Александр", "Сергей", "Дмитрий", "Андрей", "Алексей", "Максим", "Артём", "Илья",
    "Кирилл", "Никита", "Матвей", "Роман", "Егор", "Арсений", "Владислав", "Денис",
    "Павел", "Игорь", "Олег", "Юрий", "Антон", "Михаил", "Николай", "Владимир",
    "Константин", "Григорий", "Станислав", "Вадим", "Тимофей", "Марк", "Тихон",
    "Фёдор", "Захар", "Леонид", "Семён", "Платон", "Руслан", "Эдуард", "Виталий",
    "Геннадий", "Борис", "Всеволод", "Данила", "Евгений", "Карим", "Лев", "Мирон",
]
_FEMALE_FIRST = [
    "Анна", "Мария", "Елена", "Ольга", "Наталья", "Татьяна", "Ирина", "Светлана",
    "Екатерина", "Юлия", "Анастасия", "Дарья", "Полина", "Виктория", "Ксения",
    "Марина", "Оксана", "Галина", "Людмила", "Нина", "Алёна", "Кристина", "Ева",
    "Софья", "Диана", "Лариса", "Тамара", "Раиса", "Зинаида", "Инна", "Валентина",
    "Вероника", "Яна", "Эльвира", "Регина", "Милана", "Алина", "Ульяна", "Варвара",
    "Белла", "Валерия", "Василиса", "Доминика", "Есения", "Жанна", "Злата", "Изабелла",
]
_MALE_SURNAMES = [
    "Иванов", "Смирнов", "Кузнецов", "Попов", "Васильев", "Петров", "Соколов",
    "Михайлов", "Новиков", "Фёдоров", "Морозов", "Волков", "Алексеев", "Лебедев",
    "Семёнов", "Егоров", "Павлов", "Козлов", "Степанов", "Николаев", "Орлов",
    "Андреев", "Макаров", "Никитин", "Захаров", "Зайцев", "Соловьёв", "Борисов",
    "Яковлев", "Григорьев", "Романов", "Воробьёв", "Сергеев", "Кузьмин", "Фролов",
    "Александров", "Дмитриев", "Королёв", "Гусев", "Киселёв", "Ильин", "Поляков",
    "Сорокин", "Виноградов", "Ковалёв", "Белов", "Медведев", "Антонов", "Тарасов",
    "Жуков", "Баранов", "Филиппов", "Комаров", "Давыдов",
]
_PATRONYMIC_M = ("ович", "евич", "ич")
_PATRONYMIC_F = ("овна", "евна", "ична")
_PASSPORT_WEIGHTS = (10, 9, 8, 7, 6, 5, 4, 3, 2)


def _feminine_surname(surname: str) -> str:
    for old, new in (
        ("ский", "ская"), ("цкий", "цкая"), ("ской", "ская"), ("цкой", "цкая"),
        ("хой", "хая"), ("гой", "гая"),
        ("ов", "ова"), ("ев", "ева"), ("ёв", "ёва"), ("ин", "ина"), ("ын", "ына"),
        ("ий", "ая"), ("ый", "ая"), ("ой", "ая"),
    ):
        if surname.endswith(old):
            return surname[: -len(old)] + new
    return surname + "а"


def _patronymic(rnd: random.Random, female: bool) -> str:
    base = rnd.choice(_MALE_FIRST)
    if base.endswith("ий"):
        base = base[:-2] + "и"
    elif base.endswith("ь"):
        base = base[:-1]
    elif base.endswith("й"):
        base = base[:-1] + "е"
    return base + rnd.choice(_PATRONYMIC_F if female else _PATRONYMIC_M)


def _ddmmyyyy(rnd: random.Random, year: int) -> str:
    month = rnd.randint(1, 12)
    day = rnd.randint(1, calendar.monthrange(year, month)[1])
    return f"{day:02d}.{month:02d}.{year:04d}"


def _passport_number(rnd: random.Random) -> str:
    while True:
        series = f"{rnd.randint(1, 99):02d}{rnd.randint(0, 99):02d}"
        body = f"{rnd.randint(0, 99999):05d}"
        total = sum(int(d) * w for d, w in zip(series + body, _PASSPORT_WEIGHTS))
        chk = total % 11
        if chk != 10:
            return series + body + str(chk)


def _synthetic_identity(user) -> dict:
    seed = (getattr(user, "id", None) or getattr(user, "telegram_user_id", None)
            or getattr(user, "username", None) or "anon")
    rnd = random.Random(f"prontopay-synth-kyc-{seed}")
    gender = getattr(user, "gender", None)
    female = gender == "FEMALE" or (gender not in ("MALE", "FEMALE") and rnd.random() < 0.5)
    first = rnd.choice(_FEMALE_FIRST if female else _MALE_FIRST)
    last = rnd.choice(_MALE_SURNAMES)
    if female:
        last = _feminine_surname(last)
    today_year = date.today().year
    birth_year = today_year - rnd.randint(22, 55)
    birth_date = _ddmmyyyy(rnd, birth_year)
    earliest_issue = birth_year + 18
    issue_year = rnd.randint(earliest_issue, today_year - 1) if earliest_issue <= today_year - 1 else today_year - 1
    return {
        "first_name": first,
        "last_name": last,
        "patronymic": _patronymic(rnd, female),
        "birth_date": birth_date,
        "issue_date": _ddmmyyyy(rnd, issue_year),
        "passport": _passport_number(rnd),
    }


def synthetic_ready(user) -> bool:
    return bool(
        getattr(user, "kyc_status", None) is None
        and getattr(user, "kyc_session_id", None) == SYNTHETIC_KYC_SESSION
        and getattr(user, "kyc_first_name", None)
        and getattr(user, "kyc_last_name", None)
        and getattr(user, "kyc_birth_date", None)
        and getattr(user, "kyc_passport", None)
    )


def ensure_synthetic_identity(user) -> bool:
    """Keep real KYC sessions and any existing real identity data intact.

    A non-successful session still belongs to NeuroVision: replacing its key
    would prevent the callback from finding the user. Existing data without
    the synthetic marker must likewise never be replaced by a fallback.
    """
    if getattr(user, "kyc_status", None) is not None:
        return False
    session_id = getattr(user, "kyc_session_id", None)
    if session_id not in (None, "", SYNTHETIC_KYC_SESSION):
        return False
    if session_id != SYNTHETIC_KYC_SESSION and any(
        getattr(user, field, None) for field in (
            "kyc_first_name", "kyc_last_name", "kyc_patronymic",
            "kyc_birth_date", "kyc_passport", "kyc_passport_issue_date",
        )
    ):
        return False
    if synthetic_ready(user):
        return True
    ident = _synthetic_identity(user)
    user.kyc_first_name = ident["first_name"]
    user.kyc_last_name = ident["last_name"]
    user.kyc_patronymic = ident["patronymic"]
    user.kyc_birth_date = ident["birth_date"]
    user.kyc_passport = ident["passport"]
    user.kyc_passport_issue_date = ident["issue_date"]
    user.kyc_session_id = SYNTHETIC_KYC_SESSION
    return True


def card_provider_identity(user):
    """Isolate the Online provider fallback from the NeuroVision session.

    A pending/failed real session must remain available to its callback. The
    provider's non-SBP flow receives a separate view, never an ORM mutation.
    """
    if kyc_ready(user) or synthetic_ready(user):
        return user
    from types import SimpleNamespace
    identity = SimpleNamespace(**{key: getattr(user, key, None) for key in (
        "id", "telegram_user_id", "username", "gender", "email", "phone", "client_seq",
    )})
    ensure_synthetic_identity(identity)
    return identity
