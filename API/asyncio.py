import asyncio
import aiohttp
import time
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

TOKEN_URL = os.getenv("TOKEN_URL")  # shared across all APIs


@dataclass
class APIConfig:
    name: str
    client_id: str
    client_secret: str
    scope: str


APIS: dict[str, APIConfig] = {
    "api_a": APIConfig(
        name="API A",
        client_id=os.getenv("API_A_CLIENT_ID"),
        client_secret=os.getenv("API_A_CLIENT_SECRET"),
        scope=os.getenv("API_A_SCOPE"),
    ),
    "api_b": APIConfig(
        name="API B",
        client_id=os.getenv("API_B_CLIENT_ID"),
        client_secret=os.getenv("API_B_CLIENT_SECRET"),
        scope=os.getenv("API_B_SCOPE"),
    ),
    "api_c": APIConfig(
        name="API C",
        client_id=os.getenv("API_C_CLIENT_ID"),
        client_secret=os.getenv("API_C_CLIENT_SECRET"),
        scope=os.getenv("API_C_SCOPE"),
    ),
}


# ── Auth manager ──────────────────────────────────────────────────────────────

class AsyncOAuthManager:
    def __init__(self, config: APIConfig):
        self.config = config
        self._token: str | None = None
        self._expires_at: float = 0
        self._lock = asyncio.Lock()  # prevents token stampede on concurrent calls

    async def get_token(self, session: aiohttp.ClientSession) -> str:
        async with self._lock:
            if self._token and time.time() < self._expires_at - 30:
                return self._token  # still valid — reuse
            return await self._refresh_token(session)

    async def _refresh_token(self, session: aiohttp.ClientSession) -> str:
        async with session.post(TOKEN_URL, data={
            "grant_type": "client_credentials",
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "scope": self.config.scope,
        }) as resp:
            resp.raise_for_status()
            data = await resp.json()
            self._token = data["access_token"]
            self._expires_at = time.time() + data.get("expires_in", 3600)
            print(f"[{self.config.name}] Token refreshed, expires in {data.get('expires_in', 3600)}s")
            return self._token

    async def get_headers(self, session: aiohttp.ClientSession) -> dict:
        return {"Authorization": f"Bearer {await self.get_token(session)}"}

    async def request(
        self,
        session: aiohttp.ClientSession,
        method: str,
        url: str,
        **kwargs,
    ) -> dict:
        """Make a request, auto-retrying once on 401 (e.g. server-side revocation)."""
        headers = await self.get_headers(session)
        async with session.request(method, url, headers=headers, **kwargs) as resp:
            if resp.status == 401:
                # Force token refresh and retry once
                self._token = None
                headers = await self.get_headers(session)
                async with session.request(method, url, headers=headers, **kwargs) as retry_resp:
                    retry_resp.raise_for_status()
                    return await retry_resp.json()
            resp.raise_for_status()
            return await resp.json()


# ── Parallel calls ────────────────────────────────────────────────────────────

async def fetch_user(
    session: aiohttp.ClientSession,
    manager: AsyncOAuthManager,
    user_id: int,
) -> dict:
    return await manager.request(session, "GET", f"https://api-a.com/users/{user_id}")


async def fetch_orders(
    session: aiohttp.ClientSession,
    manager: AsyncOAuthManager,
    account_id: str,
) -> dict:
    return await manager.request(session, "GET", f"https://api-b.com/orders?account={account_id}")


async def fetch_user_with_orders(
    session: aiohttp.ClientSession,
    managers: dict[str, AsyncOAuthManager],
    user_id: int,
) -> dict:
    """Sequential within a single user chain, parallel across all users."""
    user = await fetch_user(session, managers["api_a"], user_id)
    orders = await fetch_orders(session, managers["api_b"], user["account_id"])
    return {"user": user, "orders": orders}


async def main():
    managers = {key: AsyncOAuthManager(cfg) for key, cfg in APIS.items()}

    # Rate-limit guard: max 5 concurrent requests at a time
    sem = asyncio.Semaphore(5)

    async def guarded_fetch(user_id: int):
        async with sem:
            return await fetch_user_with_orders(session, managers, user_id)

    user_ids = list(range(1, 21))  # 20 users

    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            *[guarded_fetch(uid) for uid in user_ids],
            return_exceptions=True,  # one failure won't cancel the rest
        )

    # Handle results
    for user_id, result in zip(user_ids, results):
        if isinstance(result, Exception):
            print(f"[user {user_id}] Failed: {result}")
        else:
            print(f"[user {user_id}] OK — {len(result['orders'])} orders")


if __name__ == "__main__":
    asyncio.run(main())