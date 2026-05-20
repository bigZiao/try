from functools import lru_cache
from pathlib import Path
import os
import re

from dotenv import load_dotenv

load_dotenv()
load_dotenv("miyao.env", override=True)


def load_powershell_env(path: str = "miyao.env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    pattern = re.compile(r"^\s*\$env:([A-Za-z_][A-Za-z0-9_]*)\s*=\s*['\"]?(.*?)['\"]?\s*$")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            os.environ[match.group(1)] = match.group(2)


load_powershell_env()


class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/app.db")
    upload_dir: Path = Path(os.getenv("UPLOAD_DIR", "uploads"))
    ocr_provider: str = os.getenv("OCR_PROVIDER", "mock")
    ocr_mock_json_path: Path | None = (
        Path(os.getenv("OCR_MOCK_JSON_PATH")) if os.getenv("OCR_MOCK_JSON_PATH") else None
    )
    llm_provider: str = os.getenv("LLM_PROVIDER", "mock")

    baidu_api_key: str | None = os.getenv("BAIDU_OCR_API_KEY")
    baidu_secret_key: str | None = os.getenv("BAIDU_OCR_SECRET_KEY")
    baidu_endpoint: str = os.getenv(
        "BAIDU_OCR_ENDPOINT",
        "https://aip.baidubce.com/rest/2.0/ocr/v1/accurate",
    )

    llm_api_url: str | None = os.getenv("LLM_API_URL")
    llm_api_key: str | None = os.getenv("LLM_API_KEY")
    llm_model: str = os.getenv("LLM_MODEL", "deepseek-reasoner")
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

    vision_llm_provider: str = os.getenv("VISION_LLM_PROVIDER", "mock")
    vision_llm_api_key: str | None = (
        os.getenv("VISION_LLM_API_KEY")
        or os.getenv("ARK_API_KEY")
        or os.getenv("DOUBAO_API_KEY")
        or llm_api_key
    )
    vision_llm_model: str = os.getenv("VISION_LLM_MODEL", "doubao-1-5-vision-pro-32k-250115")
    vision_llm_base_url: str = os.getenv("VISION_LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")

    batch_processing_concurrency: int = int(os.getenv("BATCH_PROCESSING_CONCURRENCY", "3"))
    ocr_concurrency: int = int(os.getenv("OCR_CONCURRENCY", "5"))
    llm_concurrency: int = int(os.getenv("LLM_CONCURRENCY", "2"))
    vision_llm_concurrency: int = int(os.getenv("VISION_LLM_CONCURRENCY", "1"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
