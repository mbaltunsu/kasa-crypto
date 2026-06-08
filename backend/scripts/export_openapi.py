import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
SHARED_PYTHON = REPO_ROOT / "packages" / "shared" / "python"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SHARED_PYTHON))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "openapi-export-only")
os.environ.setdefault(
    "MASTER_MNEMONIC",
    "test test test test test test test test test test test junk",
)
os.environ.setdefault("RPC_ETHEREUM_SEPOLIA", "http://localhost")
os.environ.setdefault("RPC_AVALANCHE_FUJI", "http://localhost")

from app.main import create_app  # noqa: E402


def main() -> None:
    out = REPO_ROOT / "packages" / "shared" / "openapi.json"
    schema = create_app().openapi()
    out.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
