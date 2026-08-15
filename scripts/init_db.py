"""
MangoPoint Database Initialization Script
=========================================
Run this script to initialize the database tables.

Usage:
    python -m scripts.init_db
"""

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


async def main():
    """Initialize database tables and provision the default admin user."""
    print("=" * 50)
    print("MangoPoint Database Initialization")
    print("=" * 50)

    try:
        from api.core.config import settings
        from api.core.database import async_session_maker, init_db
        from api.core.security import AuthConfigurationError
        from api.services.auth_service import auth_service

        # Register ORM models with Base.metadata
        import db.models  # noqa: F401

        print(f"\nDatabase URL: {settings.DATABASE_URL.split('@')[-1]}")
        print("Initializing tables...")

        await init_db()

        admin_status = "disabled"
        admin_user = None
        admin_error = None
        try:
            async with async_session_maker() as session:
                admin_status, admin_user = await auth_service.ensure_default_admin(session)
                await session.commit()
        except AuthConfigurationError as exc:
            admin_error = str(exc)
        except Exception as exc:
            admin_error = str(exc)

        print("\n[OK] Database initialized successfully!")
        print("\nCreated tables:")
        print("  - user_account")
        print("  - orchard")
        print("  - tree")
        print("  - pest")
        print("  - simulation_run")
        print("  - infestation_record")
        print("  - environmental_condition")
        print("  - mango_stage")
        print("  - alert")
        print("  - weather_cache")

        if settings.DEFAULT_ADMIN_ENABLED:
            if admin_error:
                print(f"\nDefault admin not provisioned: {admin_error}")
            elif admin_user is not None and admin_status == "created":
                print("\nDefault admin account created:")
                print(f"  username: {admin_user.username}")
                print(f"  email:    {admin_user.email}")
            elif admin_user is not None and admin_status == "updated":
                print("\nDefault admin account updated from .env:")
                print(f"  username: {admin_user.username}")
                print(f"  email:    {admin_user.email}")
            elif admin_user is not None:
                print("\nDefault admin already exists:")
                print(f"  username: {admin_user.username}")
                print(f"  email:    {admin_user.email}")

            if settings.DEFAULT_ADMIN_PASSWORD == "change-this-admin-password":
                print("  password: change-this-admin-password  [change immediately]")
        else:
            print("\nDefault admin provisioning is disabled (DEFAULT_ADMIN_ENABLED=false).")

        try:
            from scripts.register_orchard_assets import register_assets

            print("\nRegistering existing orchard assets...")
            created_assets, skipped_assets = await register_assets()
            print(
                f"Registered {created_assets} orchard asset(s); "
                f"skipped {skipped_assets} missing or unsafe path(s)."
            )
        except Exception as asset_error:
            print(f"\nExisting orchard asset registration skipped: {asset_error}")

    except Exception as exc:
        print(f"\n[ERROR] {exc}")
        print("\nMake sure:")
        print("  1. PostgreSQL is running")
        print("  2. Database 'mangopoint' exists")
        print("  3. PostGIS extension is enabled")
        print("\nCreate database:")
        print("  psql -U postgres")
        print("  CREATE DATABASE mangopoint;")
        print("  \\c mangopoint")
        print("  CREATE EXTENSION postgis;")
        sys.exit(1)
    finally:
        from api.core.database import close_db

        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
