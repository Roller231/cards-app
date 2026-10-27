"""Billing identity shown in the card's "Данные карты" sheet: a random name
plus a real address in the card's issuing country.

- O-Plata cards (Singapore): English name + Singapore HDB block with its
  postal code.
- Rocketpay "Pay" cards (BIN 49387519, Hong Kong): HK-style name (English
  given name + Cantonese surname) + a residential block in a Hong Kong estate.

Generated once when a card row is created and stored on the card, so it never
changes for that card. Cards created before this existed keep the old shared
template (the frontend falls back to it when the fields are empty).
"""
import random
from typing import Dict, Optional

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

# Hong Kong: English given name + common Cantonese surname, as HK cards read
_HK_SURNAMES = [
    "Chan", "Wong", "Lee", "Cheung", "Lau", "Ho", "Leung", "Ng", "Yip", "Tsang",
    "Lam", "Chow", "Tam", "Kwok", "Fung", "Mak", "Yeung", "Chu", "Lo", "Choi",
]
# Residential blocks: (building, estate + street address, area), every entry
# checked against the HK Government Address Lookup Service (als.gov.hk) on
# 2026-10-27. Hong Kong has no postal codes.
_HK_ADDRESSES = [
    ("Block 10", "Heng Fa Chuen, 100 Shing Tai Road", "Chai Wan, Hong Kong Island"),
    ("Yuan Kung Mansion", "Taikoo Shing, 20 Taikoo Shing Road", "Quarry Bay, Hong Kong Island"),
    ("Kornhill Block A", "Kornhill, 31 Hong Shing Street", "Quarry Bay, Hong Kong Island"),
    ("Hoi Fai Court (Tower 2)", "South Horizons, 2 South Horizon Drive", "Ap Lei Chau, Hong Kong Island"),
    ("Block 18", "Laguna City, 5 Laguna Street", "Kwun Tong, Kowloon"),
    ("Block E", "Amoy Gardens, 77 Ngau Tau Kok Road", "Ngau Tau Kok, Kowloon"),
    ("Block A", "Telford Gardens, 33 Wai Yip Street", "Kowloon Bay, Kowloon"),
    ("Block 6", "Whampoa Garden, 6 Tak Hong Street", "Hung Hom, Kowloon"),
    ("Mei Foo Sun Chuen", "1 Broadway", "Lai Chi Kok, Kowloon"),
    ("Block 20", "City One Shatin, 1 Tak Wing Street", "Sha Tin, New Territories"),
    ("Tower 6", "Lohas Park, 1 Lohas Park Road", "Tseung Kwan O, New Territories"),
    ("Block 1", "Discovery Park, 398 Castle Peak Road", "Tsuen Wan, New Territories"),
    ("Hoi Chu Mansion (Tower 2)", "Riviera Gardens, 1 Yi Hong Street", "Tsuen Wan, New Territories"),
]


def _is_hong_kong(offer_id: Optional[str]) -> bool:
    return str(offer_id or "").startswith("ROCKETPAY")


def generate(offer_id: Optional[str] = None) -> Dict[str, Optional[str]]:
    rnd = random.SystemRandom()
    if _is_hong_kong(offer_id):
        building, street, area = rnd.choice(_HK_ADDRESSES)
        flat = f"Flat {rnd.randint(3, 28)}{rnd.choice('ABCDEFGH')}"
        return {
            "billing_name": f"{rnd.choice(_FIRST_NAMES)} {rnd.choice(_HK_SURNAMES)}",
            "billing_address": f"{flat}, {building}, {street}, {area}",
            "billing_postal": None,
            "billing_country": "Hong Kong",
        }
    block, street, postal = rnd.choice(_ADDRESSES)
    unit = f"#{rnd.randint(2, 14):02d}-{rnd.randint(101, 499)}"
    return {
        "billing_name": f"{rnd.choice(_FIRST_NAMES)} {rnd.choice(_LAST_NAMES)}",
        "billing_address": f"{block} {street} {unit}",
        "billing_postal": postal,
        "billing_country": "Singapore",
    }
