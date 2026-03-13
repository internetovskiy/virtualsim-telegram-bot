import aiohttp
from typing import Optional, Dict
from config import settings


class CryptoBotAPI:
    def __init__(self):
        self.base_url = settings.CRYPTOBOT_BASE_URL
        self.headers = {
            "Crypto-Pay-API-Token": settings.CRYPTOBOT_API_KEY,
            "Content-Type": "application/json"
        }
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=self.headers)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _post(self, method: str, data: Dict = None) -> Dict:
        session = await self._get_session()
        async with session.post(f"{self.base_url}/{method}", json=data or {}) as resp:
            return await resp.json()

    async def _get(self, method: str, params: Dict = None) -> Dict:
        session = await self._get_session()
        async with session.get(f"{self.base_url}/{method}", params=params or {}) as resp:
            return await resp.json()

    async def create_invoice(self, amount: float, currency: str = "USDT", payload: str = "") -> Dict:
        data = {
            "asset": currency,
            "amount": str(amount),
            "description": f"Пополнение баланса VirtualSim Bot",
            "payload": payload,
            "paid_btn_name": "callback",
            "paid_btn_url": "https://t.me/your_bot",
            "allow_comments": False,
            "allow_anonymous": False,
            "expires_in": 3600
        }
        return await self._post("createInvoice", data)

    async def get_invoices(self, invoice_ids: list = None, status: str = None) -> Dict:
        params = {}
        if invoice_ids:
            params["invoice_ids"] = ",".join(map(str, invoice_ids))
        if status:
            params["status"] = status
        return await self._get("getInvoices", params)

    async def check_invoice(self, invoice_id: str) -> Optional[Dict]:
        result = await self.get_invoices(invoice_ids=[invoice_id])
        if result.get("ok") and result["result"]["items"]:
            return result["result"]["items"][0]
        return None

    async def get_me(self) -> Dict:
        return await self._get("getMe")


cryptobot = CryptoBotAPI()
