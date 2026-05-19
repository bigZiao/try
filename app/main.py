from fastapi import FastAPI

import app.models  # noqa: F401
from app.api.v1.batches import router as batches_router
from app.api.v1.receipts import router as receipts_router
from app.core.bootstrap import ensure_dev_sqlite_schema
from app.core.database import Base, engine


def create_app() -> FastAPI:
    Base.metadata.create_all(bind=engine)
    ensure_dev_sqlite_schema()

    app = FastAPI(title="Clothing Wholesale Receipt OCR Backend MVP")
    app.include_router(batches_router, prefix="/api/v1")
    app.include_router(receipts_router, prefix="/api/v1")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
