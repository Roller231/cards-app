"""Billing identity shown in the card's "Данные карты" sheet: a random
English name plus a real Singapore HDB address with its postal code.

Generated once when a card row is created and stored on the card, so it never
changes for that card. Cards created before this existed keep the old shared
template (the frontend falls back to it when the fields are empty).
"""
import random
from typing import Dict

_FIRST_NAMES = [
    "Howard", "Daniel", "Michael", "Andrew", "Ryan", "Brandon", "Kevin", "Jason",
    "Nathan", "Adrian", "Marcus", "Gabriel", "Ethan", "Lucas", "Oliver", "Samuel",
    "Victor", "Edward", "Henry", "Simon", "Alan", "Derek", "Leon", "Felix",
    "Emily", "Sarah", "Rachel", "Grace", "Chloe", "Hannah", "Olivia", "Sophie",
    "Natalie", "Vanessa", "Claire", "Megan", "Laura", "Jessica", "Amanda", "Irene",
]
_LAST_NAMES = [
    "Willis", "Turner", "Parker", "Collins", "Bennett", "Morgan", "Hughes", "Foster",
    "Russell", "Spencer", "Fletcher", "Harper", "Lawson", "Mitchell", "Porter", "Reed",
    "Sullivan", "Walsh", "Ward", "Watson", "Wells", "Palmer", "Grant", "Hayes",
    "Tan", "Lim", "Lee", "Ng", "Wong", "Chua", "Goh", "Teo",
]

# Real HDB blocks: (block, street, postal code), every entry checked against
# OneMap (Singapore Land Authority address search) on 2026-10-27.
_ADDRESSES = [
    ("160", "Lorong 1 Toa Payoh", "310160"),
    ("190", "Lorong 6 Toa Payoh", "310190"),
    ("251", "Kim Keat Link", "310251"),
    ("335", "Ang Mo Kio Avenue 1", "560335"),
    ("409", "Ang Mo Kio Avenue 10", "560409"),
    ("201", "Tampines Street 21", "520201"),
    ("539", "Bedok North Street 3", "460539"),
    ("455", "Jurong West Street 42", "640455"),
    ("845", "Yishun Street 81", "760845"),
    ("330", "Clementi Avenue 2", "120330"),
    ("150", "Mei Ling Street", "141150"),
    ("54", "Commonwealth Drive", "142054"),
    ("85", "Redhill Lane", "150085"),
    ("101", "Aljunied Crescent", "380101"),
    ("17", "Upper Boon Keng Road", "380017"),
]


def generate() -> Dict[str, str]:
    rnd = random.SystemRandom()
    block, street, postal = rnd.choice(_ADDRESSES)
    unit = f"#{rnd.randint(2, 14):02d}-{rnd.randint(101, 499)}"
    return {
        "billing_name": f"{rnd.choice(_FIRST_NAMES)} {rnd.choice(_LAST_NAMES)}",
        "billing_address": f"{block} {street} {unit}",
        "billing_postal": postal,
    }
