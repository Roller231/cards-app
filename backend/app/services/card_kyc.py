"""Identity data required by our Online card flow."""


def kyc_ready(user):
    return bool(user.kyc_status == "success" and user.kyc_first_name and user.kyc_last_name
                and user.kyc_birth_date and user.kyc_passport)
