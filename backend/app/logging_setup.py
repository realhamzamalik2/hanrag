"""Logging configuration shared by the API and CLI scripts."""

from __future__ import annotations

import logging
import os
import sys

# Windows without Developer Mode cannot create symlinks; HF cache still works, just copies.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


def setup_logging(level: str = "INFO") -> None:
    # Windows consoles default to cp949 in Korea; force UTF-8 so Korean logs don't crash.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )
    for noisy in ("httpx", "httpcore", "urllib3", "huggingface_hub", "fastembed"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
