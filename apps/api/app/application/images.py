import logging
from uuid import UUID

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from app.application.teams import require_membership
from app.domain.images import IMAGE_PREFIX, ImageStorage, ImageStorageUnavailable, OptimizedImage
from app.domain.policies import Conflict, NotFound, Permission
from app.infrastructure.models import Player, Team

logger = logging.getLogger(__name__)


def own_player(session: Session, user_id: UUID, *, lock: bool = False) -> Player:
    query = select(Player).where(Player.user_id == user_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    player = session.scalar(query)
    if player is None:
        raise Conflict("Complete seu perfil antes de adicionar uma foto.")
    return player


def managed_team(session: Session, user_id: UUID, team_id: UUID, *, lock: bool = False) -> Team:
    if lock:
        session.scalar(
            select(Team)
            .where(Team.id == team_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    return require_membership(
        session, user_id=user_id, team_id=team_id, permission=Permission.MANAGE_TEAM
    )


def discard(storage: ImageStorage, reference: str | None) -> None:
    if reference and reference.startswith(IMAGE_PREFIX):
        try:
            storage.delete(reference.removeprefix(IMAGE_PREFIX))
        except (OSError, ValueError):
            # The committed reference stays valid. Unreferenced files are never served.
            logger.warning("Unable to delete unreferenced image; storage cleanup required")


def replace_image(
    session: Session,
    owner: Player | Team,
    field: str,
    image: OptimizedImage | None,
    storage: ImageStorage,
) -> None:
    previous: str | None = getattr(owner, field)
    reference = None
    if image is not None:
        try:
            reference = IMAGE_PREFIX + storage.put(image)
        except OSError:
            raise ImageStorageUnavailable(
                "Não foi possível salvar a imagem. Tente novamente."
            ) from None
    try:
        setattr(owner, field, reference)
        session.commit()
    except Exception:
        session.rollback()
        discard(storage, reference)
        raise
    discard(storage, previous)


def save_photo(
    session: Session, user_id: UUID, image: OptimizedImage | None, storage: ImageStorage
) -> None:
    replace_image(session, own_player(session, user_id, lock=True), "photo_url", image, storage)


def save_crest(
    session: Session,
    user_id: UUID,
    team_id: UUID,
    image: OptimizedImage | None,
    storage: ImageStorage,
) -> Team:
    team = managed_team(session, user_id, team_id, lock=True)
    replace_image(session, team, "crest_url", image, storage)
    return team


def read_image(session: Session, key: str, storage: ImageStorage) -> bytes:
    reference = IMAGE_PREFIX + key
    referenced = session.scalar(
        select(
            or_(
                exists().where(Player.photo_url == reference),
                exists().where(Team.crest_url == reference),
            )
        )
    )
    if not referenced:
        raise NotFound("Imagem não encontrada")
    try:
        return storage.read(key)
    except (OSError, ValueError):
        raise NotFound("Imagem não encontrada") from None
