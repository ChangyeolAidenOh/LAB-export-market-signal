"""Load secrets from .env at the project root. Never commit .env."""

import os
import sys
from pathlib import Path
from urllib.parse import unquote

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def get_env(name: str, required: bool = True) -> str:
    val = os.environ.get(name, "")
    if not val and required:
        sys.exit(f"{name} is not set in .env")
    if "%" in val:
        val = unquote(val)
    return val
