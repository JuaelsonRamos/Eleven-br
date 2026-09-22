"""Single normalization boundary for registration, login and contact correction."""

import re
from typing import Literal

from email_validator import EmailNotValidError, validate_email

Channel = Literal["email", "phone"]


def normalize_contact(value: str) -> tuple[Channel, str]:
    value = value.strip()
    if "@" in value:
        try:
            email = validate_email(value, check_deliverability=False).normalized.lower()
        except EmailNotValidError as error:
            raise ValueError("Informe um e-mail válido.") from error
        if len(email) > 254:
            raise ValueError("Informe um e-mail válido.")
        return "email", email
    if not re.fullmatch(r"[+\d\s().-]+", value):
        raise ValueError("Informe um celular com DDD ou um e-mail válido.")
    digits = re.sub(r"\D", "", value)
    if not value.startswith("+"):
        if len(digits) == 11:
            digits = "55" + digits
        elif not (len(digits) == 13 and digits.startswith("55")):
            raise ValueError("Informe seu celular com DDD, por exemplo (11) 99999-9999.")
    if not re.fullmatch(r"[1-9]\d{7,14}", digits):
        raise ValueError("Informe um telefone internacional válido.")
    if digits.startswith("55"):
        ddds = {
            "11",
            "12",
            "13",
            "14",
            "15",
            "16",
            "17",
            "18",
            "19",
            "21",
            "22",
            "24",
            "27",
            "28",
            "31",
            "32",
            "33",
            "34",
            "35",
            "37",
            "38",
            "41",
            "42",
            "43",
            "44",
            "45",
            "46",
            "47",
            "48",
            "49",
            "51",
            "53",
            "54",
            "55",
            "61",
            "62",
            "63",
            "64",
            "65",
            "66",
            "67",
            "68",
            "69",
            "71",
            "73",
            "74",
            "75",
            "77",
            "79",
            "81",
            "82",
            "83",
            "84",
            "85",
            "86",
            "87",
            "88",
            "89",
            "91",
            "92",
            "93",
            "94",
            "95",
            "96",
            "97",
            "98",
            "99",
        }
        if len(digits) != 13 or digits[2:4] not in ddds or digits[4] != "9":
            raise ValueError("Informe um celular brasileiro com DDD e nove dígitos.")
    return "phone", "+" + digits
