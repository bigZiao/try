from fastapi import FastAPI

from app.api.v1.receipts import router as receipts_router
from app.core.database import Base, engine


def create_app() -> FastAPI:
    Base.metadata.create_all(bind=engine)

    app = FastAPI(title="Clothing Wholesale Receipt OCR Backend MVP")
    app.include_router(receipts_router, prefix="/api/v1")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
