from dataclasses import dataclass
from typing import Protocol

from app.domain.policies import DomainError

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
IMAGE_PREFIX = "/v1/media/"


class InvalidImage(DomainError):
    pass


class ImageStorageUnavailable(DomainError):
    pass


@dataclass(frozen=True)
class OptimizedImage:
    content: bytes
    extension: str


class ImageStorage(Protocol):
    def put(self, image: OptimizedImage) -> str: ...
    def read(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
