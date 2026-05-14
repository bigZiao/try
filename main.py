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
from tavily import TavilyClient


console = Console()
OUTPUT_DIR = Path("outputs")
REPORT_PATH = OUTPUT_DIR / "report.md"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"


class SearchResult(BaseModel):
    """搜索结果的数据结构。"""

    title: str = Field(description="来源标题")
    url: str = Field(description="来源 URL")
    content: str = Field(description="搜索结果摘要或正文片段")
    score: float = Field(default=0.0, description="Tavily 返回的相关性分数")


class EvidenceCard(BaseModel):
    """证据卡片的数据结构。"""

    source_title: str = Field(description="来源标题")
    url: str = Field(description="来源 URL")
    summary: str = Field(description="证据摘要")
    credibility_score: int = Field(ge=0, le=100, description="可信度评分，0 到 100")


class EvidenceCards(BaseModel):
    """证据卡片列表的数据结构。"""

    cards: list[EvidenceCard] = Field(default_factory=list, description="证据卡片列表")


def load_settings() -> tuple[str, str, str]:
    """从 .env 读取 DeepSeek、Tavily 配置。"""
    load_dotenv()
    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    tavily_api_key = os.getenv("TAVILY_API_KEY")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    if not deepseek_api_key:
        raise RuntimeError("缺少 DEEPSEEK_API_KEY。也可以临时用 OPENAI_API_KEY 作为兼容回退。")
    if not tavily_api_key:
        raise RuntimeError("缺少 TAVILY_API_KEY。请在 .env 中配置。")

    return deepseek_api_key, tavily_api_key, model


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
    """调用 DeepSeek 并尽量解析 JSON 响应。"""
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


def generate_search_queries(client: OpenAI, model: str, question: str) -> list[str]:
    """根据研究问题生成搜索词。"""
    system_prompt = "你是研究助理。请只输出 JSON，不要输出多余文字。"
    user_prompt = f"""
请围绕下面的研究问题生成 4 个适合 Tavily 搜索的搜索词。
要求：
- 覆盖事实、数据、反方观点、最新进展
- 搜索词要简洁
- 输出格式必须是：{{"queries": ["搜索词1", "搜索词2"]}}

研究问题：{question}
"""
    data = call_deepseek_json(client, model, system_prompt, user_prompt)
    queries = data.get("queries", [])
    cleaned = [str(query).strip() for query in queries if str(query).strip()]

    if question not in cleaned:
        cleaned.insert(0, question)

    return cleaned[:5]


def search_tavily(api_key: str, queries: list[str]) -> list[SearchResult]:
    """调用 Tavily 搜索并收集原始结果。"""
    client = TavilyClient(api_key=api_key)
    collected: list[SearchResult] = []

    for query in queries:
        response = client.search(
            query=query,
            search_depth="advanced",
            max_results=5,
            include_answer=False,
            include_raw_content=False,
        )
        for item in response.get("results", []):
            collected.append(
                SearchResult(
                    title=item.get("title") or "Untitled",
                    url=item.get("url") or "",
                    content=item.get("content") or "",
                    score=float(item.get("score") or 0.0),
                )
            )

    return collected


def organize_search_results(results: list[SearchResult], limit: int = 12) -> list[SearchResult]:
    """整理搜索结果，按 URL 去重并保留高相关来源。"""
    seen_urls: set[str] = set()
    unique_results: list[SearchResult] = []

    for result in sorted(results, key=lambda item: item.score, reverse=True):
        if not result.url or result.url in seen_urls:
            continue
        seen_urls.add(result.url)
        unique_results.append(result)

    return unique_results[:limit]


def format_sources_for_prompt(results: list[SearchResult]) -> str:
    """把搜索结果整理成适合模型阅读的文本材料。"""
    blocks = []
    for index, result in enumerate(results, start=1):
        blocks.append(
            f"""[{index}]
标题：{result.title}
URL：{result.url}
相关性分数：{result.score:.3f}
摘要：{result.content}
"""
        )
    return "\n".join(blocks)


def extract_evidence_cards(client: OpenAI, model: str, question: str, results: list[SearchResult]) -> list[EvidenceCard]:
    """调用 DeepSeek 从搜索结果中提取证据卡片。"""
    system_prompt = "你是严谨的研究分析师。请只输出 JSON，不要输出多余文字。"
    user_prompt = f"""
请基于搜索材料，为研究问题提取 6 到 10 条证据卡片。

研究问题：{question}

要求：
- 每条证据必须来自给定材料
- 每条证据必须包含 source_title、url、summary、credibility_score
- credibility_score 是 0 到 100 的整数，综合考虑来源权威性、信息具体程度、与问题相关性
- summary 用中文，简洁说明这条证据支持什么判断
- 输出格式必须是：{{"cards": [{{"source_title": "...", "url": "...", "summary": "...", "credibility_score": 80}}]}}

搜索材料：
{format_sources_for_prompt(results)}
"""
    data = call_deepseek_json(client, model, system_prompt, user_prompt)

    try:
        cards = EvidenceCards.model_validate(data).cards
    except ValidationError as exc:
        raise RuntimeError(f"DeepSeek 返回的证据卡片格式不正确：{exc}") from exc

    return cards


def generate_markdown_report(
    client: OpenAI,
    model: str,
    question: str,
    cards: list[EvidenceCard],
    sources: list[SearchResult],
) -> str:
    """调用 DeepSeek 生成 Markdown 研究报告。"""
    evidence_json = json.dumps([card.model_dump() for card in cards], ensure_ascii=False, indent=2)
    source_json = json.dumps([source.model_dump() for source in sources], ensure_ascii=False, indent=2)
    system_prompt = "你是专业研究报告撰写人。输出 Markdown，不要包裹代码块。"
    user_prompt = f"""
请根据证据卡片生成一份中文 Markdown 研究报告。

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
- “关键证据”中的每条证据都要包含来源标题、URL、摘要、可信度评分
- “来源列表”列出所有使用到的来源标题和 URL
- 不要编造来源，不要使用搜索材料之外的信息
- 对结论保持审慎，明确不确定性

证据卡片：
{evidence_json}

整理后的搜索来源：
{source_json}
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
    """串联执行完整 Deep Research Agent 流程。"""
    question = get_research_question()
    deepseek_api_key, tavily_api_key, model = load_settings()
    deepseek_client = build_deepseek_client(deepseek_api_key)

    console.print(Panel.fit(f"研究问题：{question}", title="Deep Research Agent"))

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        task = progress.add_task("生成搜索词", total=None)
        queries = generate_search_queries(deepseek_client, model, question)

        progress.update(task, description="调用 Tavily 搜索")
        raw_results = search_tavily(tavily_api_key, queries)

        progress.update(task, description="整理搜索结果")
        sources = organize_search_results(raw_results)

        if not sources:
            raise RuntimeError("没有获得可用搜索结果，请换一个研究问题或检查 Tavily API。")

        progress.update(task, description="提取证据卡片")
        cards = extract_evidence_cards(deepseek_client, model, question, sources)

        progress.update(task, description="生成 Markdown 研究报告")
        report = generate_markdown_report(deepseek_client, model, question, cards, sources)

        progress.update(task, description="保存报告")
        path = save_report(report)
        progress.stop_task(task)

    console.print(f"[green]完成：[/green]{path}")
    console.print(f"[cyan]搜索词：[/cyan]{', '.join(queries)}")


def main() -> None:
    """程序入口，统一处理错误展示。"""
    try:
        run()
    except Exception as exc:
        console.print(f"[red]运行失败：[/red]{exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
