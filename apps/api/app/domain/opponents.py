"""Opponent discovery, challenges and official fixtures between two registered teams.

Match dates/times are local. "Now" and the monthly competence use São Paulo, like
commercial billing, so the Free discovery credit renews deterministically without jobs.
"""

from datetime import date, datetime, time
from enum import StrEnum
from zoneinfo import ZoneInfo

LOCAL = ZoneInfo("America/Sao_Paulo")
ALL_CATEGORIES = "all"  # Explicit choice; the only filter that includes teams without category.
PAGE_SIZE = 20


class ChallengeStatus(StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class Venue(StrEnum):
    """Home or away from the challenger's point of view; neutral grounds are not defined."""

    HOME = "HOME"
    AWAY = "AWAY"


class Side(StrEnum):
    HOME = "HOME"
    AWAY = "AWAY"

    @property
    def other(self) -> "Side":
        return Side.AWAY if self is Side.HOME else Side.HOME


class ResultStatus(StrEnum):
    NONE = "NONE"  # No score reported.
    PENDING = "PENDING"  # One side reported; not official.
    VALIDATED = "VALIDATED"  # Both sides agree: the only official result.
    DISPUTED = "DISPUTED"  # Different scores; never resolved automatically.


def local_now() -> datetime:
    """Naive São Paulo wall clock, comparable with local match dates and times."""
    return datetime.now(LOCAL).replace(tzinfo=None)


def competence(now: datetime) -> date:
    return now.date().replace(day=1)


def started(day: date, at: time, now: datetime) -> bool:
    return datetime.combine(day, at) <= now
