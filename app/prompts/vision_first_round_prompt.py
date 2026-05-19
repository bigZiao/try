import json
from typing import Any


VISION_FIRST_ROUND_PROMPT = """
你是专业的服装批发票据视觉解析专家。

你将同时看到票据原图和 OCR JSON。OCR 文字、坐标、行归属都可能有错误，尤其是手写票据、拍照倾斜、纸张弯曲、表格密集、颜色/数量/单价/小计上下错位时。

任务：
优先参考原图视觉信息，结合 OCR JSON，重新解析票据信息，输出与普通第一轮完全一致的标准结构化 JSON。

解析原则：
1. 原图视觉信息优先，OCR JSON 用作辅助证据。
2. OCR block 的 top/left 坐标可能有误差，不要只按最近坐标归属字段。
3. 遇到表格行冲突时，要重建整张商品表，而不是局部修一个字段。
4. 优先选择能同时满足“行数量 × 单价 = 行小计”“尺码数量之和 = 行数量”“所有行小计之和 = 总金额”的整体解释。
5. 不允许编造原图或 OCR 中不存在的信息。
6. 如果无法唯一确定，设置 need_review=true，并在 warnings 中说明冲突点。
7. size 字段只放概括性尺码描述；多尺码数量放入 sizes 数组。
8. 输出必须是严格 JSON，不要输出 Markdown、解释文字或注释。

请输出标准结构化 JSON，字段包括：
parse_status, bill_type, merchant_name, order_date, customer_name, customer_phone, order_no, salesperson, items, summary, payments, warnings, confidence, confidence_reason, need_review。

人工复核原因：
{{REASON}}

OCR JSON：
{{OCR_RESULT}}
"""


def get_vision_first_round_prompt() -> str:
    return VISION_FIRST_ROUND_PROMPT.strip()


def render_vision_first_round_prompt(ocr_json: dict[str, Any], reason: str | None = None) -> str:
    prompt = get_vision_first_round_prompt()
    prompt = prompt.replace("{{REASON}}", reason or "未提供")
    prompt = prompt.replace("{{OCR_RESULT}}", json.dumps(ocr_json, ensure_ascii=False, indent=2))
    return prompt
