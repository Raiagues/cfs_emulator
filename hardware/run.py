"""Compatibility entry point for the Flight Studio run command."""
import os
from pathlib import Path


def main():
    start = Path(__file__).resolve().parents[1] / "start"
    os.execv(start, [str(start), "--no-ui", "run"])


if __name__ == "__main__":
    main()
