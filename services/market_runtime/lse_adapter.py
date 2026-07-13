from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Iterable, List, Optional

from .catalog import instrument_from_catalog
from .contracts import Instrument, Tick


try:
    import lse
except Exception:  # noqa: BLE001
    lse = None


class LSEAdapter:
    def __init__(
        self,
        api_key: Optional[str] = None,
        client_factory: Optional[Callable[..., Any]] = None,
    ) -> None:
        if client_factory is None:
            if lse is None:
                raise ImportError("lse-data is not installed")
            client_factory = lse.LSE
        self._client_factory = client_factory
        self._api_key = api_key
        self._client: Any = None

    @property
    def client(self) -> Any:
        if self._client is None:
            kwargs: dict[str, Any] = {}
            if self._api_key:
                kwargs["api_key"] = self._api_key
            self._client = self._client_factory(**kwargs)
        return self._client

    def catalog(self, category: Optional[str] = None) -> List[Instrument]:
        rows = self.client.catalog(category)
        return [self._to_instrument(row) for row in rows]

    @staticmethod
    def _to_instrument(row: dict) -> Instrument:
        return instrument_from_catalog(
            symbol=row["symbol"],
            name=row.get("name") or row["symbol"],
            category=row.get("category", "unknown"),
            explicitly_tradable=None,
        )

    def stream(self, symbols: Iterable[str], start: Optional[str] = None) -> Iterable[Tick]:
        for lse_tick in self.client.stream(list(symbols), start=start):
            yield self._to_tick(lse_tick)

    @staticmethod
    def _to_tick(lse_tick: Any) -> Tick:
        received_at = datetime.now(timezone.utc)
        market_asof = lse_tick.datetime or received_at
        return Tick(
            instrument_id=lse_tick.symbol,
            price=float(lse_tick.price),
            size=float(lse_tick.volume) if lse_tick.volume is not None else 0.0,
            market_asof=market_asof,
            received_at=received_at,
            event_id=lse_tick.timestamp,
        )

    def disconnect(self) -> None:
        if self._client is not None:
            self._client.disconnect()

    def __enter__(self) -> "LSEAdapter":
        return self

    def __exit__(self, *exc: Any) -> bool:
        self.disconnect()
        return False
