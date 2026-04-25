from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional, Tuple, Union

import aiohttp

from config import settings

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=60, connect=20, sock_read=50)


def _err(message: str, *, status: int = 0, raw: str = "") -> Dict[str, Any]:
    d: Dict[str, Any] = {"error": message}
    if status:
        d["http_status"] = status
    if raw:
        d["raw"] = raw[:800]
    return d


class VirtualSimAPI:
    def __init__(self) -> None:
        self.base_url = settings.VIRTUALSIM_BASE_URL.rstrip("/")
        self.api_key = (settings.VIRTUALSIM_API_KEY or "").strip()
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=DEFAULT_TIMEOUT)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    def _q(self, extra: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        out: Dict[str, str] = {"api_key": self.api_key}
        if not extra:
            return out
        for k, v in extra.items():
            if v is None:
                continue
            out[str(k)] = str(v)
        return out

    async def _request(
        self,
        method: str,
        path: str,
        *,
        query: Optional[Dict[str, Any]] = None,
        json_body: Any = None,
    ) -> Tuple[Union[Dict, None], int]:
        if not self.api_key:
            return _err("VIRTUALSIM_API_KEY is not set"), 0

        rel = path.lstrip("/")
        url = f"{self.base_url}/{rel}"
        session = await self._get_session()

        headers: Dict[str, str] = {"Accept": "application/json"}
        if json_body is not None:
            headers["Content-Type"] = "application/json"

        try:
            if method.upper() == "GET":
                async with session.get(url, params=self._q(query), headers=headers) as resp:
                    return await self._read_response(resp)
            async with session.post(
                url,
                params=self._q(None),
                json=json_body if json_body is not None else {},
                headers=headers,
            ) as resp:
                return await self._read_response(resp)
        except aiohttp.ClientError as e:
            logger.warning("VirtualSim %s %s: %s", method, rel, e)
            return _err(f"network: {e!s}"), 0

    async def _read_response(self, resp: aiohttp.ClientResponse) -> Tuple[Union[Dict, None], int]:
        status = resp.status
        text = await resp.text()

        if status == 204:
            return None, 204

        if not text.strip():
            return _err("empty body", status=status), status

        try:
            data: Union[Dict, list] = json.loads(text)
        except json.JSONDecodeError:
            return _err("invalid_json", status=status, raw=text), status

        if isinstance(data, list):
            return {"_data": data}, status

        if not isinstance(data, dict):
            return _err("unexpected_type", status=status), status

        if status >= 400 and "error" not in data:
            msg = str(
                data.get("message")
                or data.get("detail")
                or f"HTTP {status}"
            )
            data = {"error": msg, **{k: v for k, v in data.items() if k not in ("message", "detail")}}

        data["_http_status"] = status
        return data, status

    async def get_balance(self) -> Dict[str, Any]:
        d, _ = await self._request("GET", "getBalance")
        return d if isinstance(d, dict) else _err("no data")

    async def get_countries(self) -> Dict[str, Any]:
        d, _ = await self._request("GET", "getCountries")
        return d if isinstance(d, dict) else _err("no data")

    async def get_services(self) -> Dict[str, Any]:
        d, _ = await self._request("GET", "getServices")
        return d if isinstance(d, dict) else _err("no data")

    async def get_prices(
        self, service: Optional[str] = None, country: Optional[int] = None
    ) -> Dict[str, Any]:
        q: Dict[str, Any] = {}
        if service:
            q["service"] = service
        if country is not None:
            q["country"] = country
        d, _ = await self._request("GET", "getPrices", query=q or None)
        return d if isinstance(d, dict) else _err("no data")

    async def order_number(self, service: str, country: int) -> Dict[str, Any]:
        d, _ = await self._request(
            "POST",
            "orderNumber",
            json_body={"service": service, "country": int(country)},
        )
        return d if isinstance(d, dict) else _err("no data")

    async def get_status(self, activation_id: str) -> Dict[str, Any]:
        d, _ = await self._request("GET", "getStatus", query={"id": str(activation_id)})
        return d if isinstance(d, dict) else _err("no data")

    async def set_status(self, activation_id: str, status: int) -> Dict[str, Any]:
        d, _ = await self._request(
            "POST",
            "setStatus",
            json_body={"id": str(activation_id), "status": int(status)},
        )
        return d if isinstance(d, dict) else _err("no data")

    async def get_active_activations(self) -> Dict[str, Any]:
        d, _ = await self._request("GET", "getActiveActivations")
        return d if isinstance(d, dict) else _err("no data")


virtualsim = VirtualSimAPI()
