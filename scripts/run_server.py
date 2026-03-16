"""
MangoPoint Server Runner
=========================
Convenience script to run the FastAPI server.

Usage:
    python -m scripts.run_server [--port PORT] [--reload]
"""

import argparse
import importlib
import sys
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def load_uvicorn():
    """Load uvicorn with a clearer installation error message."""
    try:
        import uvicorn
    except ModuleNotFoundError:
        print("Error: missing `uvicorn`.")
        print("Install API dependencies with `pip install -r requirements-api.txt`.")
        sys.exit(1)

    return uvicorn


def preflight_api_import():
    """Check that the API application imports cleanly before starting uvicorn."""
    try:
        importlib.import_module("api.main")
    except ModuleNotFoundError as exc:
        missing = exc.name or "unknown"
        if missing.startswith("api"):
            print("Error: could not resolve `api.main` from the project root.")
            print(f"Expected project root: {PROJECT_ROOT}")
        else:
            print(f"Error: missing Python package `{missing}` while importing `api.main`.")
            print("Install API dependencies with `pip install -r requirements-api.txt`.")
        return False
    except Exception:
        print("Error: `api.main` failed during startup preflight.")
        traceback.print_exc()
        return False

    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run MangoPoint API server")
    parser.add_argument("--port", type=int, default=8000, help="Port to run on")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args(argv)

    uvicorn = load_uvicorn()

    if not preflight_api_import():
        sys.exit(1)

    print("=" * 50)
    print("MangoPoint API Server")
    print("=" * 50)
    print(f"Starting server on http://{args.host}:{args.port}")
    print(f"API Documentation: http://localhost:{args.port}/docs")
    print("=" * 50)

    run_kwargs = {
        "host": args.host,
        "port": args.port,
        "reload": args.reload,
        "log_level": "info",
    }
    if args.reload:
        run_kwargs["reload_dirs"] = [str(PROJECT_ROOT)]

    uvicorn.run(
        "api.main:app",
        **run_kwargs,
    )


if __name__ == "__main__":
    main()
