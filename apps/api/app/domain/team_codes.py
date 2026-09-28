"""Public team codes, including links containing an explicit team_code parameter."""

import re
from urllib.parse import parse_qs, urlsplit


def normalize_code(value: str) -> str:
    value = value.strip()
    if value.lower().startswith(("https://", "http://")):
        try:
            codes = parse_qs(urlsplit(value).query).get("team_code", [])
            if len(codes) == 1:
                value = codes[0]
        except ValueError:
            pass
    return re.sub(r"[\s-]+", "", value).upper()
