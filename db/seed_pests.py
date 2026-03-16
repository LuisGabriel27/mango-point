"""
MangoPoint — Pest Seed Data Script
=====================================
Inserts the required pest species into the 'pest' table.

Usage:
    python -m db.seed_pests

Idempotent: uses name-based duplicate check, safe to run multiple times.
"""

import os
import sys
from pathlib import Path

import psycopg2


DEFAULT_DB_URL = "postgresql://postgres:postgres@localhost:5433/mangopoint"

PEST_SEED_DATA = [
    {
        "name": "Mango Cecid Fly",
        "scientific_name": "Procontarinia spp.",
        "attack_stage": "fruitlet",
    },
    {
        "name": "Oriental Fruit Fly",
        "scientific_name": "Bactrocera dorsalis",
        "attack_stage": "mature",
    },
]


def parse_db_url(url: str) -> dict:
    """Parse a PostgreSQL URL into psycopg2 connection params."""
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    url = url.replace("postgresql://", "")
    user_pass, host_db = url.split("@", 1)
    user, password = user_pass.split(":", 1)
    host_port, dbname = host_db.split("/", 1)
    if ":" in host_port:
        host, port = host_port.split(":", 1)
    else:
        host, port = host_port, "5433"
    return {
        "dbname": dbname,
        "user": user,
        "password": password,
        "host": host,
        "port": int(port),
    }


def main():
    db_url = os.environ.get("DATABASE_URL", DEFAULT_DB_URL)

    print("=" * 55)
    print("MangoPoint — Pest Seed Data")
    print("=" * 55)
    print(f"\nDatabase: {db_url.split('@')[-1]}")

    conn_params = parse_db_url(db_url)
    try:
        conn = psycopg2.connect(**conn_params)
    except Exception as e:
        print(f"\n✗ Connection failed: {e}")
        sys.exit(1)

    try:
        with conn.cursor() as cur:
            for pest in PEST_SEED_DATA:
                # Check if pest already exists
                cur.execute(
                    "SELECT pest_id FROM pest WHERE name = %s;",
                    (pest["name"],),
                )
                if cur.fetchone():
                    print(f"  ℹ '{pest['name']}' already exists — skipped")
                    continue

                cur.execute(
                    """
                    INSERT INTO pest (name, scientific_name, attack_stage)
                    VALUES (%s, %s, %s::pest_attack_stage_enum)
                    RETURNING pest_id;
                    """,
                    (pest["name"], pest["scientific_name"], pest["attack_stage"]),
                )
                pid = cur.fetchone()[0]
                print(f"  ✓ Inserted '{pest['name']}' (id={pid})")

        conn.commit()
        print("\n✓ Pest seed data complete.")
        print("\nVerify with:")
        print('  psql -d mangopoint -c "SELECT * FROM pest;"')

    except Exception as e:
        conn.rollback()
        print(f"\n✗ Seed failed: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
