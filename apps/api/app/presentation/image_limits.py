import re

from starlette.formparsers import MultiPartException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.domain.images import MAX_IMAGE_BYTES


class ImageUploadLimit:
    """Bound the complete multipart body, including chunked requests, before spooling."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or not re.fullmatch(r"/v1/(?:me/photo|teams/[^/]+/crest)", scope["path"])
        ):
            await self.app(scope, receive, send)
            return
        limit = MAX_IMAGE_BYTES + 64 * 1024  # bounded multipart overhead
        headers = dict(scope["headers"])
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            length = limit + 1
        if length > limit:
            await JSONResponse({"detail": "A imagem deve ter no máximo 5 MB."}, status_code=413)(
                scope, receive, send
            )
            return
        total = 0

        async def limited_receive() -> Message:
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > limit:
                # Starlette closes temporary multipart files when this exception occurs.
                raise MultiPartException("A imagem deve ter no máximo 5 MB.")
            return message

        await self.app(scope, limited_receive, send)
