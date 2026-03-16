"""
MangoPoint Database Initialization Script
==========================================
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
    """Initialize database tables."""
    print("=" * 50)
    print("MangoPoint Database Initialization")
    print("=" * 50)
    
    try:
        from api.core.database import init_db, engine
        from api.core.config import settings

        # Import consolidated models so Base.metadata knows about them
        import db.models  # noqa: F401
        
        print(f"\nDatabase URL: {settings.DATABASE_URL.split('@')[-1]}")
        print("Initializing tables...")
        
        await init_db()
        
        print("\n✓ Database initialized successfully!")
        print("\nCreated tables:")
        print("  - orchard")
        print("  - tree")
        print("  - pest")
        print("  - simulation_run")
        print("  - infestation_record")
        print("  - environmental_condition")
        print("  - mango_stage")
        print("  - alert")
        print("  - weather_cache")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
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
