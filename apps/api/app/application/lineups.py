import hashlib
import json
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.application.events import authorize, find_event
from app.application.team_audit import record
from app.application.team_profiles import membership_context
from app.domain.lineups import TEMPLATES
from app.domain.policies import ENTITLEMENTS, Conflict, Forbidden, NotFound, Permission, Plan
from app.domain.team_identity import Modality
from app.infrastructure.launch_models import Lineup, LineupPosition
from app.infrastructure.models import Team, TeamMembership


class SlotInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slot: int = Field(ge=0, le=10, strict=True)
    membership_id: UUID


class LineupInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=80)
    modality: Modality
    formation: str = Field(max_length=16)
    event_id: UUID | None = None
    positions: list[SlotInput] = Field(max_length=11)
    expected_version: int = Field(ge=0, strict=True)
    command_id: UUID


def require_pro(team: Team) -> None:
    if not ENTITLEMENTS[Plan(team.plan)].lineups:
        raise Forbidden("Escalação é um recurso ELEVEN BR PRO.")


def present(session: Session, item: Lineup) -> dict[str, object]:
    return {
        "id": str(item.id),
        "title": item.title,
        "modality": item.modality,
        "formation": item.formation,
        "event_id": str(item.event_id) if item.event_id else None,
        "version": item.version,
        "positions": [
            {"slot": slot.slot, "membership_id": str(slot.membership_id)}
            for slot in session.scalars(
                select(LineupPosition)
                .where(LineupPosition.lineup_id == item.id)
                .order_by(LineupPosition.slot)
            )
        ],
    }


def list_items(
    session: Session, user_id: UUID, team_id: UUID, offset: int = 0
) -> dict[str, object]:
    team = authorize(session, user_id, team_id)
    enabled = ENTITLEMENTS[Plan(team.plan)].lineups
    manage = membership_context(session, team, user_id, Permission.MANAGE_EVENTS)[1]
    items = (
        list(
            session.scalars(
                select(Lineup)
                .where(Lineup.team_id == team_id)
                .order_by(Lineup.created_at.desc(), Lineup.id)
                .offset(offset)
                .limit(21)
            )
        )
        if enabled
        else []
    )
    return {
        "enabled": enabled,
        "command_id": str(uuid4()),
        "can_manage": enabled and manage,
        "templates": {key: TEMPLATES[key] for key in team.modalities},
        "items": [
            {
                "id": str(item.id),
                "title": item.title,
                "modality": item.modality,
                "formation": item.formation,
            }
            for item in items[:20]
        ],
        "has_more": len(items) > 20,
    }


def detail(session: Session, user_id: UUID, team_id: UUID, lineup_id: UUID) -> dict[str, object]:
    team = authorize(session, user_id, team_id, write=True)
    require_pro(team)
    item = session.scalar(select(Lineup).where(Lineup.id == lineup_id, Lineup.team_id == team_id))
    if item is None:
        raise NotFound("Escalação não encontrada.")
    return present(session, item)


def save(
    session: Session, user_id: UUID, team_id: UUID, data: LineupInput, lineup_id: UUID | None = None
) -> dict[str, object]:
    try:
        team = authorize(session, user_id, team_id, write=True, manage=True)
        require_pro(team)
        template = TEMPLATES.get(data.modality, {}).get(data.formation)
        if data.modality not in team.modalities or template is None:
            raise Conflict("Escolha uma formação da modalidade do time.")
        count = sum(len(row) for row in template)
        ids = [position.membership_id for position in data.positions]
        slots = [position.slot for position in data.positions]
        if (
            len(set(ids)) != len(ids)
            or len(set(slots)) != len(slots)
            or any(slot >= count for slot in slots)
        ):
            raise Conflict("Um jogador só pode ocupar uma posição válida na escalação.")
        active = set(
            session.scalars(
                select(TeamMembership.id).where(
                    TeamMembership.team_id == team_id,
                    TeamMembership.status == "active",
                    TeamMembership.id.in_(ids),
                )
            )
        )
        if set(ids) != active:
            raise Conflict("Use somente jogadores ativos deste time.")
        if data.event_id:
            event = find_event(session, team_id, data.event_id)
            if event.status != "open" or event.modality != data.modality:
                raise Conflict("Escolha um evento aberto da mesma modalidade.")
        digest = hashlib.sha256(
            json.dumps([str(user_id), data.model_dump(mode="json")], sort_keys=True).encode()
        ).hexdigest()
        item = (
            session.scalar(select(Lineup).where(Lineup.team_id == team_id, Lineup.id == lineup_id))
            if lineup_id
            else session.scalar(
                select(Lineup).where(
                    Lineup.team_id == team_id, Lineup.command_id == data.command_id
                )
            )
        )
        if not lineup_id and item:
            if item.creation_hash != digest:
                raise Conflict("Este comando já foi usado em outra escalação.")
            return present(session, item)
        if lineup_id and item is None:
            raise NotFound("Escalação não encontrada.")
        before = present(session, item) if item else {}
        if item:
            wanted = {
                "title": data.title,
                "modality": data.modality,
                "formation": data.formation,
                "event_id": str(data.event_id) if data.event_id else None,
                "positions": [
                    p.model_dump(mode="json") for p in sorted(data.positions, key=lambda p: p.slot)
                ],
            }
            if all(before[key] == value for key, value in wanted.items()):
                return before
            if item.version != data.expected_version:
                raise Conflict("A escalação mudou. Atualize antes de salvar.")
            item.version += 1
        else:
            if data.expected_version != 0:
                raise Conflict("Versão inicial inválida.")
            item = Lineup(team_id=team_id, command_id=data.command_id, creation_hash=digest)
            session.add(item)
        item.title, item.modality, item.formation, item.event_id = (
            data.title,
            data.modality,
            data.formation,
            data.event_id,
        )
        session.flush()
        session.execute(delete(LineupPosition).where(LineupPosition.lineup_id == item.id))
        session.add_all(
            [
                LineupPosition(
                    team_id=team_id, lineup_id=item.id, membership_id=p.membership_id, slot=p.slot
                )
                for p in data.positions
            ]
        )
        session.flush()
        result = present(session, item)
        record(
            session,
            team_id,
            user_id,
            item.id,
            "LINEUP_UPDATED" if before else "LINEUP_CREATED",
            before,
            result,
        )
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
