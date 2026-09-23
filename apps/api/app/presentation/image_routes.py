from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app.application import images
from app.domain.images import MAX_IMAGE_BYTES, ImageStorage, InvalidImage
from app.infrastructure.config import get_settings
from app.infrastructure.images import KEY_PATTERN, LocalImageStorage, optimize_image
from app.presentation.dependencies import CurrentUser, SessionDep
from app.presentation.routes import me, team_response
from app.presentation.schemas import ProfileRead, TeamRead

router = APIRouter(tags=["images"])
UPLOAD_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["file"],
                    "properties": {
                        "file": {
                            "type": "string",
                            "format": "binary",
                            "description": "JPEG, PNG ou WebP, até 5 MB",
                        }
                    },
                }
            }
        },
    }
}


def get_image_storage() -> ImageStorage:
    return LocalImageStorage(get_settings().media_root)


StorageDep = Annotated[ImageStorage, Depends(get_image_storage)]


async def uploaded_image(request: Request) -> bytes:
    async with request.form(max_files=1, max_fields=0, max_part_size=MAX_IMAGE_BYTES) as form:
        if set(form.keys()) != {"file"} or not isinstance(form["file"], UploadFile):
            raise InvalidImage("Selecione uma imagem para enviar.")
        data = await form["file"].read(MAX_IMAGE_BYTES + 1)
    return data


@router.post("/v1/me/photo", response_model=ProfileRead, openapi_extra=UPLOAD_BODY)
async def photo(
    request: Request, session: SessionDep, user: CurrentUser, storage: StorageDep
) -> ProfileRead:
    await run_in_threadpool(images.own_player, session, user.id)
    data = await uploaded_image(request)
    optimized = await run_in_threadpool(optimize_image, data)
    await run_in_threadpool(images.save_photo, session, user.id, optimized, storage)
    return me(session, user)


@router.post("/v1/me/photo/remove", response_model=ProfileRead)
def remove_photo(session: SessionDep, user: CurrentUser, storage: StorageDep) -> ProfileRead:
    images.save_photo(session, user.id, None, storage)
    return me(session, user)


@router.post("/v1/teams/{team_id}/crest", response_model=TeamRead, openapi_extra=UPLOAD_BODY)
async def crest(
    team_id: UUID, request: Request, session: SessionDep, user: CurrentUser, storage: StorageDep
) -> TeamRead:
    await run_in_threadpool(images.managed_team, session, user.id, team_id)
    data = await uploaded_image(request)
    optimized = await run_in_threadpool(optimize_image, data)
    team = await run_in_threadpool(images.save_crest, session, user.id, team_id, optimized, storage)
    return team_response(team, session, user.id)


@router.post("/v1/teams/{team_id}/crest/remove", response_model=TeamRead)
def remove_crest(
    team_id: UUID, session: SessionDep, user: CurrentUser, storage: StorageDep
) -> TeamRead:
    return team_response(
        images.save_crest(session, user.id, team_id, None, storage), session, user.id
    )


@router.get("/v1/media/{key}")
def image(key: str, session: SessionDep, storage: StorageDep) -> Response:
    if not KEY_PATTERN.fullmatch(key):
        raise HTTPException(404, "Imagem não encontrada")
    return Response(
        images.read_image(session, key, storage),
        media_type="image/png" if key.endswith(".png") else "image/jpeg",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
