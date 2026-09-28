from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.launch_models import TeamAudit


def record(
    session: Session,
    team_id: UUID,
    actor_id: UUID,
    entity_id: UUID,
    action: str,
    before: dict[str, object],
    after: dict[str, object],
) -> None:
    session.add(
        TeamAudit(
            team_id=team_id,
            actor_id=actor_id,
            entity_id=entity_id,
            action=action,
            before=before,
            after=after,
        )
    )
