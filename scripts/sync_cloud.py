"""Run MangoPoint's local-to-Supabase backup synchronization."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


async def _run(args: argparse.Namespace) -> None:
    from api.services.cloud_sync_service import cloud_sync_service

    try:
        if args.loop:
            await cloud_sync_service.run_scheduler()
        else:
            result = await cloud_sync_service.run_once(limit=args.limit)
            print(json.dumps(result, indent=2, default=str))
    finally:
        await cloud_sync_service.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Synchronize MangoPoint data to Supabase.")
    parser.add_argument("--once", action="store_true", help="Run one batch; this is the default.")
    parser.add_argument("--loop", action="store_true", help="Keep running on the configured interval.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum events to process in one run.")
    args = parser.parse_args()
    if args.once and args.loop:
        parser.error("--once and --loop are mutually exclusive")
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
