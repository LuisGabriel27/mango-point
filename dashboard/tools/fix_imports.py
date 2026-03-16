"""Legacy helper to patch older dashboard imports to the refactored layout."""

from pathlib import Path


APP_PATH = Path(__file__).resolve().parent.parent / "app.py"
LEGACY_IMPORT = "from raster_utils import load_raster_as_png_b64"
UPDATED_IMPORT = """from spatial.raster_utils import load_raster_as_png_b64"""


def main() -> None:
    content = APP_PATH.read_text(encoding="utf-8")

    if UPDATED_IMPORT in content:
        print("Dashboard imports already use the refactored package paths.")
        return

    if LEGACY_IMPORT not in content:
        print("Legacy import pattern not found. No changes made.")
        return

    APP_PATH.write_text(content.replace(LEGACY_IMPORT, UPDATED_IMPORT, 1), encoding="utf-8")
    print("Dashboard imports updated successfully.")


if __name__ == "__main__":
    main()
