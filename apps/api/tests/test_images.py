from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier

import pytest
from PIL import Image
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.application import images
from app.application.teams import add_member
from app.domain.images import MAX_IMAGE_BYTES, ImageStorageUnavailable
from app.domain.policies import Permission, Plan, Role
from app.infrastructure.images import LocalImageStorage, optimize_image
from app.infrastructure.models import MembershipPermission
from app.presentation.image_routes import get_image_storage
from tests.conftest import ROOT, make_player
from tests.test_foundation import make_team
from tests.test_team_profiles import client_for


def picture(
    format: str = "JPEG", size: tuple[int, int] = (1000, 400), alpha: bool = False
) -> bytes:
    output = BytesIO()
    image = Image.new(
        "RGBA" if alpha else "RGB", size, (10, 120, 40, 120) if alpha else (10, 120, 40)
    )
    image.save(output, format=format)
    return output.getvalue()


@pytest.fixture
def storage():
    directory = (ROOT / ".local").resolve()
    directory.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="test-images-", dir=directory) as temporary:
        assert Path(temporary).resolve().is_relative_to(directory)
        yield LocalImageStorage(Path(temporary) / "images")


def image_client(session, player, storage):
    client = client_for(session, player)
    client.app.dependency_overrides[get_image_storage] = lambda: storage
    return client


def upload(client, path, data=None, name="photo.jpg", mime="image/jpeg"):
    return client.post(path, files={"file": (name, picture() if data is None else data, mime)})


def test_photo_upload_replace_remove_and_reload(
    session: Session, storage: LocalImageStorage
) -> None:
    player = make_player(session)
    client = image_client(session, player, storage)
    before = client.get("/v1/me").json()
    response = upload(client, "/v1/me/photo", name="../../app.py")
    assert response.status_code == 200, response.text
    first = response.json()["photo_url"]
    assert first.startswith("/v1/media/") and "app.py" not in first
    assert client.get("/v1/me").json()["photo_url"] == first
    result = client.get(first)
    assert result.status_code == 200 and result.headers["content-type"] == "image/jpeg"
    assert result.headers["x-content-type-options"] == "nosniff"
    with Image.open(BytesIO(result.content)) as image:
        assert image.size == (512, 205)
    replaced = upload(client, "/v1/me/photo", data=picture("PNG", alpha=True)).json()["photo_url"]
    assert replaced != first and replaced.endswith(".png")
    assert client.get(first).status_code == 404
    assert not (storage.root / first.rsplit("/", 1)[1]).exists()
    with Image.open(BytesIO(client.get(replaced).content)) as image:
        assert image.mode == "RGBA"
    removed = client.post("/v1/me/photo/remove")
    assert removed.status_code == 200 and removed.json() == before
    assert client.get(replaced).status_code == 404 and not list(storage.root.iterdir())
    assert client.post("/v1/me/photo/remove").status_code == 200


@pytest.mark.parametrize("format", ["JPEG", "PNG", "WEBP"])
def test_real_content_not_extension_or_claimed_mime(
    session: Session, storage: LocalImageStorage, format: str
) -> None:
    client = image_client(session, make_player(session), storage)
    response = upload(
        client, "/v1/me/photo", data=picture(format), name="arbitrary.exe", mime="text/plain"
    )
    assert response.status_code == 200
    assert client.get(response.json()["photo_url"]).headers["content-type"] == "image/jpeg"


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"<svg><script>alert(1)</script></svg>",
        b"not a png",
        b"\xff\xd8\xff",
        picture("GIF"),
        picture("BMP"),
    ],
    ids=["empty", "svg", "text", "truncated-jpeg", "gif", "bmp"],
)
def test_invalid_file_preserves_previous_photo(
    session: Session, storage: LocalImageStorage, data: bytes
) -> None:
    client = image_client(session, make_player(session), storage)
    old = upload(client, "/v1/me/photo").json()["photo_url"]
    response = upload(client, "/v1/me/photo", data=data, name="spoof.png", mime="image/png")
    assert response.status_code == 422
    assert client.get("/v1/me").json()["photo_url"] == old
    assert len(list(storage.root.iterdir())) == 1


def test_size_pixel_and_stream_limits(session: Session, storage: LocalImageStorage) -> None:
    client = image_client(session, make_player(session), storage)
    assert upload(client, "/v1/me/photo", b"x" * (MAX_IMAGE_BYTES + 1)).status_code == 422
    assert upload(client, "/v1/me/photo", b"x" * (MAX_IMAGE_BYTES + 100_000)).status_code == 413
    assert upload(client, "/v1/me/photo", picture("PNG", (5000, 4100))).status_code == 422
    boundary = "test-boundary"

    def chunks():
        yield (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.jpg"'
            "\r\nContent-Type: image/jpeg\r\n\r\n"
        ).encode()
        for _ in range(7):
            yield b"x" * 1024 * 1024
        yield f"\r\n--{boundary}--\r\n".encode()

    streamed = client.post(
        "/v1/me/photo",
        content=chunks(),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    assert streamed.status_code in {400, 413}
    assert "5 MB" in streamed.text
    assert not storage.root.exists()


def test_exif_orientation_metadata_and_animation() -> None:
    output = BytesIO()
    exif = Image.Exif()
    exif[274], exif[270] = 6, "private description"
    Image.new("RGB", (1000, 400)).save(output, format="JPEG", exif=exif)
    optimized = optimize_image(output.getvalue())
    with Image.open(BytesIO(optimized.content)) as result:
        assert result.size == (205, 512) and not result.getexif()
    animated = BytesIO()
    Image.new("RGBA", (20, 20), "red").save(
        animated,
        format="PNG",
        save_all=True,
        append_images=[Image.new("RGBA", (20, 20), "blue")],
        duration=100,
        loop=0,
    )
    from app.domain.images import InvalidImage

    with pytest.raises(InvalidImage, match="animação"):
        optimize_image(animated.getvalue())


def test_self_only_and_no_untrusted_ids(session: Session, storage: LocalImageStorage) -> None:
    owner, other = make_player(session), make_player(session)
    client = image_client(session, owner, storage)
    outsider = image_client(session, other, storage)
    old = upload(client, "/v1/me/photo").json()["photo_url"]
    assert upload(outsider, f"/v1/players/{owner.id}/photo").status_code == 404
    assert upload(outsider, f"/v1/users/{owner.user_id}/photo").status_code == 404
    assert (
        outsider.post(
            "/v1/me/photo",
            data={"user_id": str(owner.user_id)},
            files={"file": ("a.jpg", picture())},
        ).status_code
        == 400
    )
    assert upload(outsider, "/v1/me/photo").status_code == 200
    assert client.get("/v1/me").json()["photo_url"] == old
    assert client.post("/v1/me/photo/remove").status_code == 200
    assert outsider.get("/v1/me").json()["photo_url"] is not None
    anonymous = image_client(session, None, storage)
    assert upload(anonymous, "/v1/me/photo").status_code == 401
    assert anonymous.post("/v1/me/photo/remove").status_code == 401


def test_crest_lifecycle_permissions_and_isolation(
    session: Session, storage: LocalImageStorage
) -> None:
    owner = make_player(session)
    team, other = make_team(session, owner), make_team(session, make_player(session))
    reader = make_player(session)
    add_member(session, team_id=team.id, player_id=reader.id)
    client = image_client(session, owner, storage)
    common = image_client(session, reader, storage)
    path = f"/v1/teams/{team.id}/crest"
    before = client.get(f"/v1/teams/{team.id}").json()
    assert upload(common, path).status_code == 403
    assert common.post(path + "/remove").status_code == 403
    assert upload(client, f"/v1/teams/{other.id}/crest").status_code == 404
    assert client.post(f"/v1/teams/{other.id}/crest/remove").status_code == 404
    assert upload(image_client(session, None, storage), path).status_code == 401
    first = upload(client, path).json()["crest_url"]
    second = upload(client, path, picture("PNG", alpha=True)).json()["crest_url"]
    assert first != second and client.get(first).status_code == 404
    assert client.get(f"/v1/teams/{team.id}").json()["crest_url"] == second
    assert client.post(path + "/remove").json() == before
    assert client.get(second).status_code == 404
    assert not list(storage.root.iterdir())


def test_admin_grants_and_plan_policy(session: Session, storage: LocalImageStorage) -> None:
    team = make_team(session, make_player(session), Plan.PRO)
    admin = make_player(session)
    membership = add_member(
        session,
        team_id=team.id,
        player_id=admin.id,
        role=Role.ADMIN,
        permissions={Permission.MANAGE_MEMBERS},
    )
    client = image_client(session, admin, storage)
    path = f"/v1/teams/{team.id}/crest"
    assert upload(client, path).status_code == 403
    session.add(MembershipPermission(membership_id=membership.id, permission="manage_team"))
    session.commit()
    assert upload(client, path).status_code == 200
    team.plan = "free"
    session.commit()
    assert upload(client, path).status_code == 403
    assert client.post(path + "/remove").status_code == 403


def test_storage_and_commit_failures_keep_reference_safe(
    session: Session, storage: LocalImageStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    player = make_player(session)
    client = image_client(session, player, storage)
    old = upload(client, "/v1/me/photo").json()["photo_url"]
    user_id = player.user_id
    assert user_id
    with monkeypatch.context() as patch:

        def broken_put(image):
            raise OSError("disk unavailable")

        patch.setattr(storage, "put", broken_put)
        with pytest.raises(ImageStorageUnavailable):
            images.save_photo(session, user_id, optimize_image(picture()), storage)
    assert client.get("/v1/me").json()["photo_url"] == old
    with monkeypatch.context() as patch:

        def broken_commit():
            raise SQLAlchemyError("failed transaction")

        patch.setattr(session, "commit", broken_commit)
        with pytest.raises(SQLAlchemyError):
            images.save_photo(session, user_id, optimize_image(picture()), storage)
    assert client.get("/v1/me").json()["photo_url"] == old
    assert len(list(storage.root.iterdir())) == 1
    with monkeypatch.context() as patch:

        def broken_delete(key):
            raise OSError("locked file")

        patch.setattr(storage, "delete", broken_delete)
        new = upload(client, "/v1/me/photo").json()["photo_url"]
    assert client.get(new).status_code == 200 and client.get(old).status_code == 404
    assert len(list(storage.root.iterdir())) == 2  # orphan inaccessible despite deletion failure


def test_safe_keys_and_no_directory_serving(session: Session, storage: LocalImageStorage) -> None:
    client = image_client(session, make_player(session), storage)
    for key in ["../.env", "/.env", "..\\.env", "a.jpg", "a" * 32 + ".svg"]:
        with pytest.raises(ValueError):
            storage.read(key)
    assert client.get("/v1/media").status_code == 404
    assert client.get("/v1/media/.env").status_code == 404
    assert client.get("/v1/media/" + "a" * 32 + ".jpg").status_code == 404


def test_concurrent_replacement_no_broken_reference(
    engine: Engine, session: Session, storage: LocalImageStorage
) -> None:
    player = make_player(session)
    user_id = player.user_id
    session.commit()
    assert user_id
    barrier = Barrier(2)

    def replace(_: int) -> None:
        with Session(engine) as independent:
            barrier.wait(timeout=10)
            images.save_photo(independent, user_id, optimize_image(picture()), storage)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(replace, [1, 2]))
    session.expire_all()
    assert len(list(storage.root.iterdir())) == 1
    assert storage.read(player.photo_url.rsplit("/", 1)[1])


def test_only_image_references_change_existing_data(
    session: Session, storage: LocalImageStorage
) -> None:
    owner = make_player(session)
    team = make_team(session, owner)
    team.name = "Tabajara FC"
    client = image_client(session, owner, storage)
    from tests.test_events import DATA

    assert (
        client.post(
            f"/v1/teams/{team.id}/events", json={**DATA, "recurring_weekly": True}
        ).status_code
        == 201
    )

    def snapshot():
        return {
            table: session.execute(
                text(f'SELECT to_jsonb(t) FROM "{table}" t ORDER BY to_jsonb(t)::text')
            )
            .scalars()
            .all()
            for table in inspect(session.get_bind()).get_table_names()
            if table != "alembic_version"
        }

    before = snapshot()
    assert upload(client, "/v1/me/photo").status_code == 200
    assert upload(client, f"/v1/teams/{team.id}/crest").status_code == 200
    after = snapshot()
    for table, field in [("players", "photo_url"), ("teams", "crest_url")]:
        for rows in [before[table], after[table]]:
            for row in rows:
                row.pop(field)
                row.pop("updated_at")
    assert before == after
