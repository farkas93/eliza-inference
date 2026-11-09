"""Command-line entry point for the shared local model-artifact checks."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "eliza-cli"))

from core.model_artifacts import main

if __name__ == "__main__":
    raise SystemExit(main())
