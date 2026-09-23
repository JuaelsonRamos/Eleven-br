"""Random formation strategy, independent of persistence and permanent team identity."""

from dataclasses import dataclass
from random import SystemRandom
from typing import Literal
from uuid import UUID

from app.domain.policies import Conflict

MAX_TEAMS = 32
MAX_PARTICIPANTS = 256


@dataclass(frozen=True)
class Choice:
    kind: Literal["member", "guest"]
    source_id: UUID
    goalkeeper: bool = False


def random_teams(choices: list[Choice], count: int) -> list[list[Choice]]:
    if not 2 <= count <= min(len(choices), MAX_TEAMS) or len(choices) > MAX_PARTICIPANTS:
        raise Conflict("Escolha entre 2 e 32 times, sem ultrapassar o número de participantes")
    if len({(p.kind, p.source_id) for p in choices}) != len(choices):
        raise Conflict("Não repita participantes no sorteio")
    keepers = [p for p in choices if p.goalkeeper]
    others = [p for p in choices if not p.goalkeeper]
    random = SystemRandom()
    random.shuffle(keepers)
    random.shuffle(others)
    groups: list[list[Choice]] = [[] for _ in range(count)]
    for index, person in enumerate(keepers + others):
        groups[index % count].append(person)
    return groups
