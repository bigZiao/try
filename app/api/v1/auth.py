from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.adapters.wechat import WeChatLoginAdapter
from app.core.database import get_db
from app.models.user import User
from app.schemas.auth import WeChatLoginRequest, WeChatLoginResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/wechat-login", response_model=WeChatLoginResponse)
async def wechat_login(payload: WeChatLoginRequest, db: Session = Depends(get_db)) -> WeChatLoginResponse:
    try:
        session = await WeChatLoginAdapter().code_to_session(payload.code)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    openid = session.get("openid")
    if not openid:
        raise HTTPException(status_code=400, detail="WeChat openid is missing")

    user = db.query(User).filter(User.openid == openid).first()
    if user is None:
        user = User(
            display_name=payload.display_name or "老板",
            phone=payload.phone,
            openid=openid,
            session_key=session.get("session_key"),
            role="owner",
            status="active",
            is_admin=False,
        )
        db.add(user)
    else:
        user.session_key = session.get("session_key") or user.session_key
        if payload.display_name:
            user.display_name = payload.display_name
        if payload.phone:
            user.phone = payload.phone
    db.commit()
    db.refresh(user)
    return WeChatLoginResponse(user=user, access_token=str(user.id))
