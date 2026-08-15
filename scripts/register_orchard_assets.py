"""Register existing local orchard files in the cloud-backup asset manifest."""

import asyncio
import hashlib
import mimetypes
import sys
from pathlib import Path

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

ASSET_COLUMNS = (
    ("tree_geojson", "tree_geojson_path"),
    ("orthophoto", "orthophoto_path"),
    ("orthophoto_png", "orthophoto_png_path"),
    ("dtm", "dtm_path"),
    ("dsm", "dsm_path"),
)


def _manifest(path: Path, asset_type: str) -> dict:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "asset_type": asset_type,
        "local_path": path.relative_to(PROJECT_ROOT).as_posix(),
        "sha256": digest.hexdigest(),
        "file_size": path.stat().st_size,
        "mime_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
    }


async def register_assets() -> tuple[int, int]:
    from api.core.database import async_session_maker
    from db.models import Orchard, OrchardAsset

    created = 0
    skipped = 0
    asset_root = (PROJECT_ROOT / "data" / "orchards").resolve()
    async with async_session_maker() as db:
        orchards = (await db.execute(select(Orchard))).scalars().all()
        for orchard in orchards:
            for asset_type, column_name in ASSET_COLUMNS:
                raw_path = getattr(orchard, column_name, None)
                if not raw_path:
                    continue
                path = (PROJECT_ROOT / raw_path).resolve()
                if asset_root not in path.parents or not path.exists():
                    skipped += 1
                    continue
                exists = await db.scalar(
                    select(OrchardAsset.asset_id).where(
                        OrchardAsset.orchard_id == orchard.orchard_id,
                        OrchardAsset.asset_type == asset_type,
                    )
                )
                if exists:
                    continue
                db.add(OrchardAsset(orchard_id=orchard.orchard_id, **_manifest(path, asset_type)))
                created += 1
        await db.commit()

    return created, skipped


async def main() -> int:
    from api.core.database import close_db

    try:
        created, skipped = await register_assets()
    finally:
        await close_db()

    print(f"Registered {created} orchard asset(s); skipped {skipped} missing or unsafe path(s).")
    return created


if __name__ == "__main__":
    asyncio.run(main())
