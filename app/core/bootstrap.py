from sqlalchemy import text

from app.core.database import engine, settings


def ensure_dev_sqlite_schema() -> None:
    if not settings.database_url.startswith("sqlite"):
        return

    with engine.begin() as connection:
        receipt_columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(receipts)")).fetchall()
        }
        add_columns = {
            "user_id": "INTEGER NOT NULL DEFAULT 1",
            "batch_id": "INTEGER",
            "image_sha256": "VARCHAR(64) NOT NULL DEFAULT ''",
            "duplicate_of_receipt_id": "INTEGER",
            "duplicate_status": "VARCHAR(50) NOT NULL DEFAULT 'unique'",
        }
        for column, definition in add_columns.items():
            if column not in receipt_columns:
                connection.execute(text(f"ALTER TABLE receipts ADD COLUMN {column} {definition}"))

        connection.execute(
            text(
                "INSERT OR IGNORE INTO users (id, display_name, phone, openid) "
                "VALUES (1, '默认老板', NULL, NULL)"
            )
        )
