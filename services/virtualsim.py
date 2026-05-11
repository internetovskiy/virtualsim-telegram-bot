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
        d["_http_status"] = status
        d["http_status"] = status
    if raw:
        d["raw"] = raw[:800]
    return d


class VirtualSimAPI:
    def __init__(self) -> None:
        self.base_url = self._normalize_base_url(settings.VIRTUALSIM_BASE_URL)
        self.api_key = (settings.VIRTUALSIM_API_KEY or "").strip()
        self._session: Optional[aiohttp.ClientSession] = None

    @staticmethod
    def _normalize_base_url(raw: str) -> str:
        base = (raw or "https://virtualsim.io/stubs/handler_api.php").strip().rstrip("/")
        if base.endswith("/api/v1"):
            return base[: -len("/api/v1")] + "/stubs/handler_api.php"
        if base.endswith("handler_api.php"):
            return base
        return base + "/stubs/handler_api.php"

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=DEFAULT_TIMEOUT)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    def _params(self, action: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        out: Dict[str, str] = {"api_key": self.api_key, "action": action}
        if extra:
            for k, v in extra.items():
                if v is None:
                    continue
                out[str(k)] = str(v)
        return out

    async def _request(
        self,
        action: str,
        *,
        method: str = "GET",
        query: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Union[Dict, list, str, None], int]:
        if not self.api_key:
            return _err("VIRTUALSIM_API_KEY is not set"), 0

        session = await self._get_session()
        headers: Dict[str, str] = {"Accept": "application/json, text/plain;q=0.9, */*;q=0.8"}
        params = self._params(action, query)

        try:
            if method.upper() == "POST":
                async with session.post(self.base_url, data=params, headers=headers) as resp:
                    return await self._read_response(resp)
            async with session.get(self.base_url, params=params, headers=headers) as resp:
                return await self._read_response(resp)
        except aiohttp.ClientError as e:
            logger.warning("VirtualSim action=%s: %s", action, e)
            return _err(f"network: {e!s}"), 0

    async def _read_response(self, resp: aiohttp.ClientResponse) -> Tuple[Union[Dict, list, str, None], int]:
        status = resp.status
        text = (await resp.text()).strip()

        if status == 204:
            return {"success": True, "_http_status": 204}, 204

        if not text:
            return _err("empty body", status=status), status

        try:
            data: Union[Dict, list, str] = json.loads(text)
        except json.JSONDecodeError:
            data = text

        if isinstance(data, dict):
            if status >= 400 and "error" not in data:
                msg = str(data.get("message") or data.get("detail") or f"HTTP {status}")
                data = {"error": msg, **{k: v for k, v in data.items() if k not in ("message", "detail")}}
            data["_http_status"] = status
            return data, status

        if isinstance(data, list):
            return data, status

        if status >= 400:
            return _err(self._human_error(str(data)), status=status, raw=str(data)), status

        return str(data), status

    @staticmethod
    def _human_error(code: str) -> str:
        mapping = {
            "BAD_KEY": "Неверный API-ключ",
            "BAD_ACTION": "Метод API не найден",
            "BAD_DATA": "Некорректные параметры запроса",
            "NO_BALANCE": "Недостаточно средств на балансе VirtualSim",
            "NO_NUMBERS": "Нет доступных номеров",
            "NO_ACTIVATION": "Активация не найдена",
            "WRONG_PRICE": "Цена изменилась, обновите каталог",
            "WRONG_MAX_NUMBERS": "Достигнут лимит активных номеров",
            "CATALOG_NOT_READY": "Каталог временно недоступен",
        }
        return mapping.get(code.strip(), code.strip() or "Ошибка API")

    async def get_balance(self) -> Dict[str, Any]:
        d, status = await self._request("getBalance")
        if isinstance(d, str) and d.startswith("ACCESS_BALANCE:"):
            try:
                return {"balance": float(d.split(":", 1)[1]), "currency": "USD", "_http_status": status}
            except (TypeError, ValueError):
                return _err("bad balance response", status=status, raw=d)
        if isinstance(d, dict):
            return d
        return _err("no data", status=status, raw=str(d or ""))

    async def get_countries(self) -> Dict[str, Any]:
        d, status = await self._request("getCountries")
        if isinstance(d, list):
            return {"countries": d, "_http_status": status}
        if isinstance(d, dict):
            if "countries" not in d and "_data" in d:
                return {"countries": d["_data"], "_http_status": status}
            return d
        return _err("no data", status=status, raw=str(d or ""))

    async def get_services(self) -> Dict[str, Any]:
        d, status = await self._request("getServicesList")
        if isinstance(d, dict):
            return d
        return _err("no data", status=status, raw=str(d or ""))

    async def get_prices(
        self, service: Optional[str] = None, country: Optional[int] = None
    ) -> Dict[str, Any]:
        q: Dict[str, Any] = {}
        if service:
            q["service"] = service
        if country is not None:
            q["country"] = country
        d, status = await self._request("getPrices", query=q or None)
        if isinstance(d, dict):
            return d
        return _err("no data", status=status, raw=str(d or ""))

    async def order_number(self, service: str, country: int) -> Dict[str, Any]:
        d, status = await self._request(
            "getNumberV2",
            query={"service": service, "country": int(country)},
        )
        if isinstance(d, dict):
            if "activationCost" in d and "cost" not in d:
                d["cost"] = d.get("activationCost")
            return d
        if isinstance(d, str) and d.startswith("ACCESS_NUMBER:"):
            parts = d.split(":", 2)
            if len(parts) == 3:
                return {
                    "activationId": parts[1],
                    "phoneNumber": parts[2],
                    "cost": 0.0,
                    "currency": "USD",
                    "_http_status": status,
                }
        return _err(self._human_error(str(d or "NO_NUMBERS")), status=status, raw=str(d or ""))

    async def get_status(self, activation_id: str) -> Dict[str, Any]:
        d, status = await self._request("getStatus", query={"id": str(activation_id)})
        if isinstance(d, dict):
            return d
        if not isinstance(d, str):
            return _err("no data", status=status)

        if d.startswith("STATUS_OK:"):
            sms = d.split(":", 1)[1].strip()
            return {
                "activationId": str(activation_id),
                "status": "received",
                "smsReceived": True,
                "messages": [{"text": sms, "receivedAt": None}],
                "_http_status": status,
            }
        if d in ("STATUS_WAIT_CODE", "STATUS_WAIT_RETRY", "STATUS_WAIT_RESEND"):
            return {
                "activationId": str(activation_id),
                "status": "waiting",
                "smsReceived": False,
                "messages": [],
                "_http_status": status,
            }
        if d in ("STATUS_CANCEL", "ACCESS_CANCEL"):
            return {
                "activationId": str(activation_id),
                "status": "cancelled",
                "smsReceived": False,
                "messages": [],
                "_http_status": status,
            }
        return _err(self._human_error(d), status=status, raw=d)

    async def set_status(self, activation_id: str, status: int) -> Dict[str, Any]:
        d, http_status = await self._request(
            "setStatus",
            query={"id": str(activation_id), "status": int(status)},
        )
        if isinstance(d, dict):
            return d
        if isinstance(d, str):
            ok_prefixes = ("ACCESS_", "STATUS_", "READY")
            if d.startswith(ok_prefixes):
                return {"success": True, "result": d, "_http_status": http_status}
            return _err(self._human_error(d), status=http_status, raw=d)
        return _err("no data", status=http_status)

    async def get_active_activations(self) -> Dict[str, Any]:
        d, status = await self._request("getActiveActivations")
        if isinstance(d, dict):
            return d
        return _err("no data", status=status, raw=str(d or ""))


virtualsim = VirtualSimAPI()
