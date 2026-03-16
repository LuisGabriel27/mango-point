"""
MangoPoint — GeoJSON Tree Import Script
=========================================
Reads the QGIS-exported GeoJSON file and inserts tree records
into the 'tree' table, populating x_coordinate, y_coordinate, and geom.

Usage:
    python -m db.import_geojson
    python -m db.import_geojson --geojson path/to/custom.geojson
    python -m db.import_geojson --orchard-name "My Orchard"

Prerequisites:
    - PostgreSQL + PostGIS running
    - Database 'mangopoint' exists
    - Schema already applied (psql -f db/schema.sql OR python -m scripts.init_db)
"""

import json
import os
import sys
import argparse
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values


# Default paths
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _resolve_default_geojson() -> Path:
    for name in ("trees.geojson", "Dummy_Mango_Data.geojson"):
        candidate = _DATA_DIR / name
        if candidate.exists():
            return candidate
    return _DATA_DIR / "trees.geojson"


DEFAULT_GEOJSON = _resolve_default_geojson()
DEFAULT_DB_URL = "postgresql://postgres:postgres@localhost:5433/mangopoint"
DEFAULT_ORCHARD_NAME = "Guimaras Mango Orchard"
DEFAULT_ORCHARD_LOCATION = "Jordan, Guimaras, Philippines"


def parse_db_url(url: str) -> dict:
    """Parse a PostgreSQL URL into psycopg2 connection params."""
    # postgresql://user:password@host:port/dbname
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


def load_geojson(filepath: Path) -> dict:
    """Load and parse GeoJSON file."""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_orchard(conn, name: str, location: str) -> int:
    """
    Ensure the orchard record exists.
    Returns the orchard_id.
    """
    with conn.cursor() as cur:
        # Check if orchard already exists by name
        cur.execute("SELECT orchard_id FROM orchard WHERE name = %s;", (name,))
        row = cur.fetchone()
        if row:
            print(f"  ℹ Orchard '{name}' already exists (id={row[0]})")
            return row[0]
        
        # Insert new orchard
        cur.execute(
            """
            INSERT INTO orchard (name, location, area_size, tree_count)
            VALUES (%s, %s, NULL, 0)
            RETURNING orchard_id;
            """,
            (name, location),
        )
        orchard_id = cur.fetchone()[0]
        conn.commit()
        print(f"  ✓ Created orchard '{name}' (id={orchard_id})")
        return orchard_id


def import_trees(conn, geojson: dict, orchard_id: int) -> int:
    """
    Parse GeoJSON features and insert tree records.
    Returns the number of trees imported.
    """
    features = geojson.get("features", [])
    if not features:
        print("  ⚠ No features found in GeoJSON file.")
        return 0

    # Map GeoJSON Status to tree_status_enum
    status_map = {
        "unbagged": "healthy",
        "bagged": "bagged",
        "infected": "infected",
        "dead": "dead",
        "healthy": "healthy",
    }

    rows = []
    for feat in features:
        geom = feat.get("geometry", {})
        props = feat.get("properties", {})

        if geom.get("type") != "Point":
            continue

        coords = geom.get("coordinates", [])
        if len(coords) < 2:
            continue

        lon, lat = coords[0], coords[1]

        # Map status from GeoJSON properties
        raw_status = str(props.get("status", props.get("Status", "healthy"))).strip().lower()
        status = status_map.get(raw_status, "healthy")

        rows.append((
            orchard_id,
            lon,          # x_coordinate
            lat,          # y_coordinate
            lon, lat,     # for ST_SetSRID(ST_MakePoint(...))
            None,         # age (not in GeoJSON)
            status,
            "dormant",    # current_stage default
        ))

    if not rows:
        print("  ⚠ No valid Point features found.")
        return 0

    with conn.cursor() as cur:
        insert_sql = """
            INSERT INTO tree (
                orchard_id, x_coordinate, y_coordinate,
                geom, age, status, current_stage
            )
            VALUES %s
        """
        template = (
            "(%(orchard_id)s, %(x)s, %(y)s, "
            "ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326), "
            "%(age)s, %(status)s::tree_status_enum, %(stage)s::tree_stage_enum)"
        )

        # Use parameterised inserts for safety
        values = []
        for r in rows:
            cur.execute(
                """
                INSERT INTO tree (
                    orchard_id, x_coordinate, y_coordinate,
                    geom, age, status, current_stage
                ) VALUES (
                    %s, %s, %s,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                    %s, %s::tree_status_enum, %s::tree_stage_enum
                );
                """,
                r,
            )

        # Update orchard tree_count
        cur.execute(
            "UPDATE orchard SET tree_count = %s WHERE orchard_id = %s;",
            (len(rows), orchard_id),
        )
        conn.commit()

    return len(rows)


def main():
    parser = argparse.ArgumentParser(
        description="Import QGIS-exported GeoJSON tree points into MangoPoint database.",
    )
    parser.add_argument(
        "--geojson",
        type=Path,
        default=DEFAULT_GEOJSON,
        help=f"Path to GeoJSON file (default: {DEFAULT_GEOJSON})",
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default=os.environ.get("DATABASE_URL", DEFAULT_DB_URL),
        help="PostgreSQL connection URL",
    )
    parser.add_argument(
        "--orchard-name",
        type=str,
        default=DEFAULT_ORCHARD_NAME,
        help="Name for the orchard record",
    )
    parser.add_argument(
        "--orchard-location",
        type=str,
        default=DEFAULT_ORCHARD_LOCATION,
        help="Location description for the orchard",
    )
    args = parser.parse_args()

    print("=" * 55)
    print("MangoPoint — GeoJSON Tree Import")
    print("=" * 55)

    # Validate GeoJSON file
    if not args.geojson.exists():
        print(f"\n✗ GeoJSON file not found: {args.geojson}")
        sys.exit(1)

    print(f"\nGeoJSON file : {args.geojson}")
    print(f"Database     : {args.database_url.split('@')[-1]}")
    print(f"Orchard name : {args.orchard_name}")

    # Load GeoJSON
    print("\n[1/3] Loading GeoJSON...")
    geojson = load_geojson(args.geojson)
    n_features = len(geojson.get("features", []))
    print(f"  ✓ Loaded {n_features} features")

    # Connect to database
    print("\n[2/3] Connecting to database...")
    conn_params = parse_db_url(args.database_url)
    try:
        conn = psycopg2.connect(**conn_params)
        print("  ✓ Connected")
    except Exception as e:
        print(f"\n✗ Connection failed: {e}")
        print("\nMake sure PostgreSQL is running and the database exists.")
        sys.exit(1)

    try:
        # Ensure orchard exists
        print("\n[3/3] Importing trees...")
        orchard_id = ensure_orchard(conn, args.orchard_name, args.orchard_location)

        # Import trees
        n_imported = import_trees(conn, geojson, orchard_id)

        print(f"\n✓ Successfully imported {n_imported} trees into orchard_id={orchard_id}")
        print("\nVerify with:")
        print("  psql -d mangopoint -c \"SELECT tree_id, x_coordinate, y_coordinate, ST_AsText(geom) FROM tree LIMIT 5;\"")

    except Exception as e:
        conn.rollback()
        print(f"\n✗ Import failed: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
