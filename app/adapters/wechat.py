from typing import Any

import httpx

from app.core.config import get_settings


class WeChatLoginAdapter:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def code_to_session(self, code: str) -> dict[str, Any]:
        if self.settings.wechat_login_provider.lower() == "mock":
            return {
                "openid": f"mock_{code}",
                "session_key": "mock_session_key",
            }

        if not self.settings.wechat_app_id or not self.settings.wechat_app_secret:
            raise RuntimeError("WECHAT_APP_ID or WECHAT_APP_SECRET is missing")

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                "https://api.weixin.qq.com/sns/jscode2session",
                params={
                    "appid": self.settings.wechat_app_id,
                    "secret": self.settings.wechat_app_secret,
                    "js_code": code,
                    "grant_type": "authorization_code",
                },
            )
            response.raise_for_status()
            data = response.json()

        if data.get("errcode"):
            raise RuntimeError(f"WeChat login failed: {data}")
        return data
