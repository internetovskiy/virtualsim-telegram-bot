import aiohttp
from typing import Optional, Dict
from config import settings


class VirtualSimAPI:
    def __init__(self):
        self.base_url = settings.VIRTUALSIM_BASE_URL.rstrip("/")
        self.api_key = settings.VIRTUALSIM_API_KEY
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _inject_key(self, params: Optional[Dict]) -> Dict:
        p = dict(params or {})
        p["api_key"] = self.api_key
        return p

    async def _get(self, endpoint: str, params: Dict = None) -> Dict:
        session = await self._get_session()
        async with session.get(
            f"{self.base_url}/{endpoint}", params=self._inject_key(params)
        ) as resp:
            return await resp.json()

    async def _post(self, endpoint: str, data: Dict = None) -> Dict:
        session = await self._get_session()
        async with session.post(
            f"{self.base_url}/{endpoint}",
            params=self._inject_key(None),
            json=data,
        ) as resp:
            return await resp.json()

    async def get_balance(self) -> Dict:
        return await self._get("getBalance")

    async def get_countries(self) -> Dict:
        return await self._get("getCountries")

    async def get_services(self) -> Dict:
        return await self._get("getServices")

    async def get_prices(self, service: str = None, country: int = None) -> Dict:
        params = {}
        if service:
            params["service"] = service
        if country is not None:
            params["country"] = country
        return await self._get("getPrices", params=params)

    async def order_number(self, service: str, country: int) -> Dict:
        return await self._post("orderNumber", {"service": service, "country": country})

    async def get_status(self, activation_id: str) -> Dict:
        return await self._get("getStatus", {"id": activation_id})

    async def set_status(self, activation_id: str, status: int) -> Dict:
        return await self._post("setStatus", {"id": activation_id, "status": status})

    async def get_active_activations(self) -> Dict:
        return await self._get("getActiveActivations")


virtualsim = VirtualSimAPI()
