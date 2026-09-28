"""Global historical adjustments. All writes share the Team lock with match corrections."""

import hashlib
import json
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.policies import Conflict
from app.domain.statistics import Totals
from app.infrastructure.statistic_models import StatisticAdjustment

FIELDS = ("goals", "yellow_cards", "red_cards")


class AdjustInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: UUID
    expected_state: str = Field(min_length=64, max_length=64)
    goals: int = Field(ge=0, le=999999, strict=True)
    yellow_cards: int = Field(ge=0, le=999999, strict=True)
    red_cards: int = Field(ge=0, le=999999, strict=True)
    confirm: bool = Field(default=False, strict=True)


def sums(session: Session, team_id: UUID) -> dict[UUID, dict[str, int]]:
    rows = session.execute(
        select(
            StatisticAdjustment.membership_id,
            *[
                func.sum(getattr(StatisticAdjustment, f"{field}_delta")).label(field)
                for field in FIELDS
            ],
        )
        .where(StatisticAdjustment.team_id == team_id)
        .group_by(StatisticAdjustment.membership_id)
    ).mappings()
    return {row["membership_id"]: {field: int(row[field]) for field in FIELDS} for row in rows}


def apply_to(counts: Totals, adjustment: dict[str, int]) -> None:
    for field in FIELDS:
        # Later match corrections may remove the base underlying a negative adjustment.
        setattr(counts, field, max(0, getattr(counts, field) + adjustment.get(field, 0)))


def detail(
    session: Session, user_id: UUID, team_id: UUID, membership_id: UUID
) -> dict[str, object]:
    from app.application.events import authorize
    from app.application.statistics import profile

    authorize(session, user_id, team_id, write=True, manage=True)
    result = profile(
        session,
        user_id=user_id,
        team_id=team_id,
        person_id=membership_id,
        kind="member",
        include_adjustments=False,
    )
    person = result["person"]
    assert hasattr(person, "totals")
    base = {field: getattr(person.totals, field) for field in FIELDS}
    adjustments = sums(session, team_id).get(membership_id, dict.fromkeys(FIELDS, 0))
    state = hashlib.sha256(
        json.dumps([str(membership_id), base, adjustments], sort_keys=True).encode()
    ).hexdigest()
    return {
        "base": base,
        "adjustments": adjustments,
        "totals": {field: max(0, base[field] + adjustments[field]) for field in FIELDS},
        "floor_applied": any(base[field] + adjustments[field] < 0 for field in FIELDS),
        "expected_state": state,
        "command_id": uuid4(),
    }


def adjust(
    session: Session, user_id: UUID, team_id: UUID, membership_id: UUID, data: AdjustInput
) -> dict[str, object]:
    try:
        current = detail(session, user_id, team_id, membership_id)
        wanted = {field: getattr(data, field) for field in FIELDS}
        old = session.scalar(
            select(StatisticAdjustment).where(
                StatisticAdjustment.team_id == team_id,
                StatisticAdjustment.command_id == data.command_id,
            )
        )
        if old:
            if (
                old.membership_id != membership_id
                or old.actor_id != user_id
                or old.new_totals != wanted
                or old.expected_state != data.expected_state
            ):
                raise Conflict("Este identificador já foi usado em outro ajuste.")
            return current
        if not data.confirm:
            raise Conflict("Confirme o ajuste das estatísticas.")
        if current["expected_state"] != data.expected_state:
            raise Conflict("As estatísticas mudaram. Atualize e confira os valores novamente.")
        if wanted != current["totals"]:
            base, adjustments = current["base"], current["adjustments"]
            assert isinstance(base, dict) and isinstance(adjustments, dict)
            session.add(
                StatisticAdjustment(
                    team_id=team_id,
                    membership_id=membership_id,
                    actor_id=user_id,
                    command_id=data.command_id,
                    expected_state=data.expected_state,
                    previous_totals=current["totals"],
                    new_totals=wanted,
                    **{
                        f"{field}_delta": wanted[field] - base[field] - adjustments[field]
                        for field in FIELDS
                    },
                )
            )
            session.flush()
        result = detail(session, user_id, team_id, membership_id)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
