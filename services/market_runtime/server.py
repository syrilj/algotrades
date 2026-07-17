from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from .api import create_app
from .lse_adapter import LSEAdapter
from .persistence import TickPersistence
from .supervisor import StreamSupervisor
from .vault_client import LSEVaultClient

load_dotenv()


def _make_app():
    runtime_env = os.environ.get("MARKET_RUNTIME_ENV", "development").strip().lower()
    if runtime_env in {"production", "prod"}:
        if not os.environ.get("MARKET_RUNTIME_API_TOKEN", "").strip():
            raise RuntimeError(
                "MARKET_RUNTIME_API_TOKEN is required when MARKET_RUNTIME_ENV=production"
            )
        if not os.environ.get("LSE_API_KEY", "").strip():
            raise RuntimeError("LSE_API_KEY is required when MARKET_RUNTIME_ENV=production")
    data_dir = Path(__file__).resolve().parents[2] / "data"
    data_dir.mkdir(exist_ok=True)

    api_key = os.environ.get("LSE_API_KEY")
    adapter = LSEAdapter(api_key=api_key)

    persistence = TickPersistence(
        str(data_dir / "market_runtime.db"),
        commit_every=int(os.environ.get("MARKET_RUNTIME_TICK_COMMIT_EVERY", 100)),
    )

    supervisor = StreamSupervisor(
        adapter,
        max_symbols=int(os.environ.get("MARKET_RUNTIME_MAX_SYMBOLS", 1000)),
        persistence=persistence,
    )

    vault_client = LSEVaultClient(api_key=api_key)
    return create_app(supervisor, vault_client=vault_client)


app = _make_app()
