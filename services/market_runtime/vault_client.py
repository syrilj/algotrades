from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

import httpx


DEFAULT_VAULT_URL = "https://api.londonstrategicedge.com/vault"
REFERENCE_DATASETS = {
    "economic_calendar",
    "insider_trades",
    "dividends",
    "stock_splits",
    "cot",
    "financial_reports",
    "company_profiles",
    "stock_fundamentals",
    "bond_yields",
}


@dataclass(frozen=True)
class VaultResult:
    data: Any
    data_bytes: Optional[int] = None


class LSEVaultError(RuntimeError):
    def __init__(self, status: int, detail: str) -> None:
        self.status = int(status)
        self.detail = detail
        super().__init__(f"LSE vault [{self.status}]: {detail}")


class LSEVaultClient:
    """Small production client for the documented LSE vault REST surface.

    Authentication stays on the market-runtime server. Query calls retry only
    transient transport, 429, and 503 failures; all other client errors surface
    immediately with the provider's JSON ``detail`` message.
    """

    def __init__(
        self,
        api_key: Optional[str],
        *,
        base_url: str = DEFAULT_VAULT_URL,
        timeout_seconds: float = 15.0,
        max_retries: int = 2,
        client: Optional[httpx.Client] = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key = (api_key or "").strip()
        self._base_url = base_url.rstrip("/")
        self._max_retries = max(0, int(max_retries))
        self._sleep = sleep
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout_seconds)

    @staticmethod
    def _detail(response: httpx.Response) -> str:
        try:
            payload = response.json()
            if isinstance(payload, dict):
                detail = payload.get("detail") or payload.get("message")
                if detail:
                    return str(detail)[:500]
        except ValueError:
            pass
        return (response.text or response.reason_phrase or "request failed")[:500]

    @staticmethod
    def _retry_delay(response: Optional[httpx.Response], attempt: int) -> float:
        if response is not None:
            raw = response.headers.get("retry-after")
            if raw:
                try:
                    return min(5.0, max(0.0, float(raw)))
                except ValueError:
                    pass
        return min(2.0, 0.25 * (2**attempt))

    def _request(
        self,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
    ) -> VaultResult:
        if not self._api_key:
            raise LSEVaultError(503, "LSE_API_KEY is not configured")

        clean_params = {
            key: value
            for key, value in (params or {}).items()
            if value is not None and value != ""
        }
        headers = {
            "Accept": "application/json",
            "User-Agent": "TradingAlgoWork-market-runtime/1.0",
            "x-api-key": self._api_key,
        }

        for attempt in range(self._max_retries + 1):
            response: Optional[httpx.Response] = None
            try:
                response = self._client.get(
                    f"{self._base_url}/{path.lstrip('/')}",
                    params=clean_params,
                    headers=headers,
                )
            except httpx.RequestError as exc:
                if attempt < self._max_retries:
                    self._sleep(self._retry_delay(None, attempt))
                    continue
                raise LSEVaultError(502, f"vault transport error: {exc}") from exc

            if response.status_code in {429, 503} and attempt < self._max_retries:
                self._sleep(self._retry_delay(response, attempt))
                continue
            if not response.is_success:
                raise LSEVaultError(response.status_code, self._detail(response))

            try:
                data = response.json()
            except ValueError as exc:
                raise LSEVaultError(502, "vault returned invalid JSON") from exc

            raw_bytes = response.headers.get("x-data-bytes")
            try:
                data_bytes = int(raw_bytes) if raw_bytes is not None else None
            except ValueError:
                data_bytes = None
            return VaultResult(data=data, data_bytes=data_bytes)

        raise LSEVaultError(502, "vault request failed")  # pragma: no cover

    def usage(self) -> VaultResult:
        return self._request("usage")

    def catalog(self, dataset: Optional[str] = None) -> VaultResult:
        result = self._request("catalog")
        if dataset and isinstance(result.data, list):
            rows = [row for row in result.data if row.get("dataset") == dataset]
            return VaultResult(rows, result.data_bytes)
        return result

    def meta(self) -> VaultResult:
        return self._request("meta")

    def reference_index(self) -> VaultResult:
        return self._request("reference")

    def candles(self, **params: Any) -> VaultResult:
        return self._request("candles", params=params)

    def series(self, **params: Any) -> VaultResult:
        return self._request("series", params=params)

    def reference_rows(self, dataset: str, **params: Any) -> VaultResult:
        if dataset not in REFERENCE_DATASETS:
            raise LSEVaultError(400, f"unsupported reference dataset: {dataset}")
        return self._request(f"ref/{dataset}", params=params)

    def options_chain(self, **params: Any) -> VaultResult:
        return self._request("options/chain", params=params)

    def options_flow(self, **params: Any) -> VaultResult:
        return self._request("options/flow", params=params)

    def option_candles(self, **params: Any) -> VaultResult:
        return self._request("options/candles", params=params)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "LSEVaultClient":
        return self

    def __exit__(self, *exc: Any) -> bool:
        self.close()
        return False
