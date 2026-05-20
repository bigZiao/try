from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WeChatLoginRequest(BaseModel):
    code: str
    display_name: str | None = None
    phone: str | None = None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    display_name: str
    phone: str | None = None
    openid: str | None = None
    role: str
    status: str
    is_admin: bool
    created_at: datetime


class WeChatLoginResponse(BaseModel):
    user: UserResponse
    token_type: str = "x-user-id"
    access_token: str
