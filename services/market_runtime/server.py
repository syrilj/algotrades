from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from .api import create_app
from .lse_adapter import LSEAdapter
from .persistence import TickPersistence
from .supervisor import StreamSupervisor

load_dotenv()


def _make_app():
    data_dir = Path(__file__).resolve().parents[2] / "data"
    data_dir.mkdir(exist_ok=True)

    api_key = os.environ.get("LSE_API_KEY")
    adapter = LSEAdapter(api_key=api_key)

    persistence = TickPersistence(str(data_dir / "market_runtime.db"))

    supervisor = StreamSupervisor(
        adapter,
        max_symbols=int(os.environ.get("MARKET_RUNTIME_MAX_SYMBOLS", 1000)),
        persistence=persistence,
    )

    return create_app(supervisor)


app = _make_app()
