import re
import warnings
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

from app.domain.images import MAX_IMAGE_BYTES, MAX_IMAGE_PIXELS, InvalidImage, OptimizedImage

KEY_PATTERN = re.compile(r"[a-f0-9]{32}\.(?:jpg|png)")


def optimize_image(content: bytes) -> OptimizedImage:
    if len(content) > MAX_IMAGE_BYTES:
        raise InvalidImage("A imagem deve ter no máximo 5 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as original:
                if original.format not in {"JPEG", "PNG", "WEBP"}:
                    raise InvalidImage("Selecione uma imagem JPEG, PNG ou WebP.")
                if original.width * original.height > MAX_IMAGE_PIXELS:
                    raise InvalidImage(
                        "A imagem é grande demais. Use uma versão de até 20 megapixels."
                    )
                if getattr(original, "n_frames", 1) != 1:
                    raise InvalidImage("Use uma imagem estática, sem animação.")
                original.verify()
            with Image.open(BytesIO(content)) as original:
                original.load()
                oriented = ImageOps.exif_transpose(original)
                transparent = "A" in oriented.getbands() or "transparency" in oriented.info
                resized = oriented.convert("RGBA" if transparent else "RGB")
                resized.thumbnail((512, 512), Image.Resampling.LANCZOS)
                # A fresh image discards EXIF/GPS, comments and embedded metadata.
                clean = Image.new(resized.mode, resized.size)
                clean.paste(resized)
                output = BytesIO()
                clean.save(
                    output,
                    format="PNG" if transparent else "JPEG",
                    optimize=True,
                    **({} if transparent else {"quality": 85, "progressive": True}),
                )
                return OptimizedImage(output.getvalue(), "png" if transparent else "jpg")
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise InvalidImage(
            "Arquivo inválido. Selecione uma imagem JPEG, PNG ou WebP válida."
        ) from None


class LocalImageStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        if KEY_PATTERN.fullmatch(key) is None:
            raise ValueError("Invalid image key")
        path = self.root / key
        if path.resolve().parent != self.root:
            raise ValueError("Invalid image path")
        return path

    def put(self, image: OptimizedImage) -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        for _ in range(5):
            key = f"{uuid4().hex}.{image.extension}"
            path = self._path(key)
            try:
                with path.open("xb") as file:
                    file.write(image.content)
                return key
            except FileExistsError:
                continue
            except OSError:
                path.unlink(missing_ok=True)
                raise
        raise OSError("Could not allocate image key")

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)
