"""Code-owned templates: new tactical formations need no database migration."""

TEMPLATES: dict[str, dict[str, list[list[str]]]] = {
    "campo": {
        "4-4-2": [["GOL"], ["LE", "ZAG", "ZAG", "LD"], ["PE", "MC", "MC", "PD"], ["ATA", "ATA"]],
        "4-3-3": [["GOL"], ["LE", "ZAG", "ZAG", "LD"], ["MC", "VOL", "MEI"], ["PE", "ATA", "PD"]],
        "4-2-3-1": [
            ["GOL"],
            ["LE", "ZAG", "ZAG", "LD"],
            ["VOL", "VOL"],
            ["PE", "MEI", "PD"],
            ["ATA"],
        ],
        "3-5-2": [["GOL"], ["ZAG", "ZAG", "ZAG"], ["LE", "MC", "VOL", "MEI", "LD"], ["ATA", "ATA"]],
        "3-4-3": [["GOL"], ["ZAG", "ZAG", "ZAG"], ["LE", "MC", "MC", "LD"], ["PE", "ATA", "PD"]],
    },
    "society": {
        "2-3-1": [["GOL"], ["ZAG", "ZAG"], ["PE", "MC", "PD"], ["ATA"]],
        "3-2-1": [["GOL"], ["LE", "ZAG", "LD"], ["MC", "MEI"], ["ATA"]],
        "2-2-2": [["GOL"], ["ZAG", "ZAG"], ["MC", "MC"], ["ATA", "ATA"]],
    },
    "futsal": {
        "1-2-1": [["GOL"], ["ZAG"], ["PE", "PD"], ["ATA"]],
        "2-2": [["GOL"], ["ZAG", "MC"], ["ATA", "ATA"]],
        "3-1": [["GOL"], ["PE", "ZAG", "PD"], ["ATA"]],
    },
}
