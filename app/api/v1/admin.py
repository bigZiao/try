from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.receipt import Receipt
from app.models.user import User
from app.schemas.auth import UserResponse
from app.schemas.receipt import ReceiptResponse

router = APIRouter(prefix="/admin", tags=["admin"])


def require_admin(x_admin_token: str | None = Header(None, alias="X-Admin-Token")) -> None:
    expected = get_settings().admin_token
    if expected and x_admin_token != expected:
        raise HTTPException(status_code=403, detail="Admin token is invalid")


@router.get("/users", response_model=list[UserResponse])
def list_users(
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = 100,
) -> list[User]:
    return db.query(User).order_by(User.id.desc()).limit(min(limit, 500)).all()


@router.get("/receipts", response_model=list[ReceiptResponse])
def list_all_receipts(
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = 100,
) -> list[Receipt]:
    return db.query(Receipt).order_by(Receipt.id.desc()).limit(min(limit, 500)).all()
