"""
MangoPoint local setup checker.

Usage:
    python -m scripts.check_setup
    python -m scripts.check_setup --check-db
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def result(label: str, message: str) -> None:
    print(f"[{label}] {message}")


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def has_command(*names: str) -> bool:
    return any(shutil.which(name) for name in names)


def check_python(errors: list[str]) -> None:
    version = sys.version_info
    if version >= (3, 10):
        result("OK", f"Python {version.major}.{version.minor}.{version.micro}")
    else:
        errors.append("Python 3.10 or newer is required.")
        result("ERROR", "Python 3.10 or newer is required.")


def check_required_files(errors: list[str]) -> None:
    required_paths = [
        "requirements-api.txt",
        "run_server.py",
        "api/main.py",
        "frontend/package.json",
        "frontend/package-lock.json",
        ".env.example",
    ]
    for relative_path in required_paths:
        path = PROJECT_ROOT / relative_path
        if path.exists():
            result("OK", relative_path)
        else:
            errors.append(f"Missing required file: {relative_path}")
            result("ERROR", f"Missing required file: {relative_path}")


def check_env(warnings: list[str]) -> None:
    env_path = PROJECT_ROOT / ".env"

    if not env_path.exists():
        warnings.append("Missing .env. Copy .env.example to .env and set local values.")
        result("WARN", "Missing .env. Run: copy .env.example .env")
        return

    result("OK", ".env exists")
    env = load_env_file(env_path)

    database_url = env.get("DATABASE_URL", "")
    if database_url:
        result("OK", "DATABASE_URL is set")
    else:
        warnings.append("DATABASE_URL is not set in .env.")
        result("WARN", "DATABASE_URL is not set in .env")

    secret = env.get("AUTH_SECRET_KEY", "")
    if not secret:
        warnings.append("AUTH_SECRET_KEY is empty. Login tokens will fail.")
        result("WARN", "AUTH_SECRET_KEY is empty")
    elif secret == "replace-with-a-long-random-secret":
        warnings.append("AUTH_SECRET_KEY is still the example value.")
        result("WARN", "AUTH_SECRET_KEY is still the example value")
    else:
        result("OK", "AUTH_SECRET_KEY is set")

    admin_password = env.get("DEFAULT_ADMIN_PASSWORD", "")
    if admin_password == "change-this-admin-password":
        warnings.append("DEFAULT_ADMIN_PASSWORD is still the example value.")
        result("WARN", "DEFAULT_ADMIN_PASSWORD is still the example value")

    required_keys = ["DATABASE_URL", "AUTH_SECRET_KEY", "DEFAULT_ADMIN_PASSWORD"]
    missing_required = [key for key in required_keys if key not in env]
    if missing_required:
        warnings.append(".env is missing required local setup keys.")
        result("WARN", ".env is missing: " + ", ".join(missing_required))


def check_backend_packages(errors: list[str]) -> None:
    packages = {
        "fastapi": "fastapi",
        "uvicorn": "uvicorn",
        "pydantic_settings": "pydantic-settings",
        "sqlalchemy": "sqlalchemy",
        "asyncpg": "asyncpg",
        "numpy": "numpy",
        "pandas": "pandas",
        "geopandas": "geopandas",
        "rasterio": "rasterio",
    }

    missing = [package_name for module, package_name in packages.items() if importlib.util.find_spec(module) is None]
    if missing:
        errors.append("Missing backend packages: " + ", ".join(missing))
        result("ERROR", "Install backend packages: python -m pip install -r requirements-api.txt")
    else:
        result("OK", "Backend Python packages are installed")


def check_frontend(errors: list[str], warnings: list[str]) -> None:
    if has_command("node.exe", "node"):
        result("OK", "Node.js is available")
    else:
        errors.append("Node.js is required for the React frontend.")
        result("ERROR", "Node.js is required for the React frontend")

    if has_command("npm.cmd", "npm"):
        result("OK", "npm is available")
    else:
        errors.append("npm is required for the React frontend.")
        result("ERROR", "npm is required for the React frontend")

    node_modules = PROJECT_ROOT / "frontend" / "node_modules"
    if node_modules.exists():
        result("OK", "frontend/node_modules exists")
    else:
        warnings.append("Frontend packages are not installed. Run npm install inside frontend/.")
        result("WARN", "Frontend packages are not installed. Run: cd frontend; npm install")


async def check_database(errors: list[str]) -> None:
    try:
        from sqlalchemy import text

        from api.core.database import close_db, engine

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        result("OK", "Database connection works")
    except Exception as exc:
        errors.append(f"Database check failed: {exc}")
        result("ERROR", f"Database check failed: {exc}")
    finally:
        try:
            from api.core.database import close_db

            await close_db()
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Check MangoPoint local setup")
    parser.add_argument("--check-db", action="store_true", help="Also test the configured PostgreSQL connection")
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []

    print("MangoPoint setup check")
    print("=" * 24)

    check_python(errors)
    check_required_files(errors)
    check_env(warnings)
    check_backend_packages(errors)
    check_frontend(errors, warnings)

    if args.check_db:
        asyncio.run(check_database(errors))
    else:
        result("INFO", "Database connection not tested. Use --check-db after PostgreSQL is ready.")

    print("=" * 24)
    if errors:
        result("ERROR", f"{len(errors)} blocking issue(s) found")
        return 1
    if warnings:
        result("WARN", f"{len(warnings)} warning(s) found")
        return 0

    result("OK", "Setup looks ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
