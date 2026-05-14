import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn


console = Console()
OUTPUT_DIR = Path("outputs")
REPORT_PATH = OUTPUT_DIR / "report.md"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-pro"


class ResearchAngle(BaseModel):
    """研究角度的数据结构。"""

    query: str = Field(description="可用于人工检索或后续追踪的搜索词")
    purpose: str = Field(description="这个搜索词要验证的内容")


class ResearchAngles(BaseModel):
    """研究角度列表的数据结构。"""

    angles: list[ResearchAngle] = Field(default_factory=list, description="研究角度列表")


class EvidenceCard(BaseModel):
    """证据卡片的数据结构。"""

    source_title: str = Field(description="来源标题或建议核验来源")
    url: str = Field(description="来源 URL；没有可靠 URL 时写 N/A")
    summary: str = Field(description="证据摘要")
    credibility_score: int = Field(ge=0, le=100, description="可信度评分，0 到 100")


class EvidenceCards(BaseModel):
    """证据卡片列表的数据结构。"""

    cards: list[EvidenceCard] = Field(default_factory=list, description="证据卡片列表")


def load_settings() -> tuple[str, str]:
    """从 .env 读取 DeepSeek 配置。"""
    load_dotenv()
    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    model = os.getenv("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL)

    if not deepseek_api_key:
        raise RuntimeError("缺少 DEEPSEEK_API_KEY。也可以临时用 OPENAI_API_KEY 作为兼容回退。")

    return deepseek_api_key, model


def build_deepseek_client(api_key: str) -> OpenAI:
    """创建 DeepSeek 的 OpenAI 兼容客户端。"""
    return OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)


def get_research_question() -> str:
    """从命令行参数读取研究问题。"""
    if len(sys.argv) < 2:
        raise RuntimeError('请按这种方式运行：python main.py "用户的研究问题"')

    question = " ".join(sys.argv[1:]).strip()
    if not question:
        raise RuntimeError("研究问题不能为空。")

    return question


def call_deepseek_json(client: OpenAI, model: str, system_prompt: str, user_prompt: str) -> dict[str, Any]:
    """调用 DeepSeek 并解析 JSON 响应。"""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or "{}"
    return json.loads(content)


def call_deepseek_text(client: OpenAI, model: str, system_prompt: str, user_prompt: str) -> str:
    """调用 DeepSeek 并返回文本响应。"""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
    )
    return (response.choices[0].message.content or "").strip()


def generate_research_angles(client: OpenAI, model: str, question: str) -> list[ResearchAngle]:
    """根据研究问题生成研究角度和可人工核验的搜索词。"""
    system_prompt = "你是研究助理。请只输出 JSON，不要输出多余文字。"
    user_prompt = f"""
请围绕下面的研究问题生成 5 个研究角度。

要求：
- 覆盖事实、数据、反方观点、最新进展、后续跟踪
- query 是适合人工搜索或后续核验的搜索词
- purpose 说明这个搜索词要验证什么
- 输出格式必须是：{{"angles": [{{"query": "...", "purpose": "..."}}]}}

研究问题：{question}
"""
    data = call_deepseek_json(client, model, system_prompt, user_prompt)

    try:
        return ResearchAngles.model_validate(data).angles
    except ValidationError as exc:
        raise RuntimeError(f"DeepSeek 返回的研究角度格式不正确：{exc}") from exc


def format_angles_for_prompt(angles: list[ResearchAngle]) -> str:
    """把研究角度整理成适合模型阅读的文本。"""
    blocks = []
    for index, angle in enumerate(angles, start=1):
        blocks.append(f"{index}. 搜索词：{angle.query}\n   核验目的：{angle.purpose}")
    return "\n".join(blocks)


def extract_evidence_cards(client: OpenAI, model: str, question: str, angles: list[ResearchAngle]) -> list[EvidenceCard]:
    """调用 DeepSeek 基于模型知识生成证据卡片和建议核验来源。"""
    system_prompt = "你是严谨的研究分析师。请只输出 JSON，不要输出多余文字。"
    user_prompt = f"""
请基于你的通用知识和下面的研究角度，为研究问题生成 6 到 10 条证据卡片。

重要限制：
- 当前程序不调用搜索引擎，也不读取网页
- 不确定具体 URL 时，url 必须写 "N/A"，不要编造链接
- source_title 可以写权威机构、论文、企业报告、统计口径或“需人工核验的来源类型”
- credibility_score 需要因为“未实时检索”而更保守

研究问题：{question}

研究角度：
{format_angles_for_prompt(angles)}

输出要求：
- 每条证据必须包含 source_title、url、summary、credibility_score
- credibility_score 是 0 到 100 的整数
- summary 用中文，说明这条证据支持或削弱什么判断
- 输出格式必须是：{{"cards": [{{"source_title": "...", "url": "N/A", "summary": "...", "credibility_score": 60}}]}}
"""
    data = call_deepseek_json(client, model, system_prompt, user_prompt)

    try:
        return EvidenceCards.model_validate(data).cards
    except ValidationError as exc:
        raise RuntimeError(f"DeepSeek 返回的证据卡片格式不正确：{exc}") from exc


def generate_markdown_report(
    client: OpenAI,
    model: str,
    question: str,
    angles: list[ResearchAngle],
    cards: list[EvidenceCard],
) -> str:
    """调用 DeepSeek 生成 Markdown 研究报告。"""
    angle_json = json.dumps([angle.model_dump() for angle in angles], ensure_ascii=False, indent=2)
    evidence_json = json.dumps([card.model_dump() for card in cards], ensure_ascii=False, indent=2)
    system_prompt = "你是专业研究报告撰写人。输出 Markdown，不要包裹代码块。"
    user_prompt = f"""
请根据研究角度和证据卡片生成一份中文 Markdown 研究报告。

研究问题：{question}

报告必须包含以下一级或二级标题：
- 一句话结论
- 核心判断
- 关键证据
- 反方观点
- 不确定性
- 后续跟踪指标
- 来源列表

硬性要求：
- 报告开头必须提示：本报告未调用实时搜索，来源和结论需要人工核验
- “关键证据”中的每条证据都要包含来源标题、URL、摘要、可信度评分
- URL 为 N/A 时，要明确写“未实时检索，需人工核验”
- “来源列表”列出所有建议核验来源
- 不要编造具体网页链接
- 对结论保持审慎，明确不确定性

研究角度：
{angle_json}

证据卡片：
{evidence_json}
"""
    report = call_deepseek_text(client, model, system_prompt, user_prompt)

    if not report.startswith("#"):
        report = f"# 研究报告：{question}\n\n{report}"

    return report


def save_report(markdown: str) -> Path:
    """保存 Markdown 报告到 outputs/report.md。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(markdown, encoding="utf-8")
    return REPORT_PATH


def run() -> None:
    """串联执行 DeepSeek-only 研究 Agent 流程。"""
    question = get_research_question()
    deepseek_api_key, model = load_settings()
    deepseek_client = build_deepseek_client(deepseek_api_key)

    console.print(Panel.fit(f"研究问题：{question}", title="DeepSeek Research Agent"))

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        task = progress.add_task("生成研究角度", total=None)
        angles = generate_research_angles(deepseek_client, model, question)

        progress.update(task, description="生成证据卡片")
        cards = extract_evidence_cards(deepseek_client, model, question, angles)

        progress.update(task, description="生成 Markdown 研究报告")
        report = generate_markdown_report(deepseek_client, model, question, angles, cards)

        progress.update(task, description="保存报告")
        path = save_report(report)
        progress.stop_task(task)

    console.print(f"[green]完成：[/green]{path}")
    console.print(f"[cyan]模型：[/cyan]{model}")


def main() -> None:
    """程序入口，统一处理错误展示。"""
    try:
        run()
    except Exception as exc:
        console.print(f"[red]运行失败：[/red]{exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
