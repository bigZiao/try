import json
from typing import Any


SECOND_ROUND_PROMPT = """
你是专业的服装批发票据 JSON 纠错专家。

下面给你：
1. OCR 原始结果
2. 第一轮结构化 JSON
3. 规则引擎校验错误

你的任务是只针对规则错误相关字段进行纠错，输出修正后的完整 JSON。

纠错原则：

1. 可以修正 JSON，但修正结果还会交给规则引擎复验。
2. 不允许为了让规则通过而编造 OCR 中不存在的信息。
3. 每个修正必须有 OCR 证据、坐标证据或业务规则证据。
4. 如果存在多个可能修正方案，不要强行选择，设置 need_review=true。
5. 优先修正可计算字段：数量、单价、小计、总数量、总金额、应收金额、收款金额、欠款金额。
6. 谨慎修正款号、商品名称、颜色、客户名、手机号、订单号、日期。
7. 不要把底部银行账号、电话、二维码文字当成支付或客户信息。
8. 不要把“款数”当成“数量”，不要把“本次欠款”当成“收款金额”。
9. 本业务的单尺码描述通常是概括性尺码，例如均码、小、中、大、S、M、L、XL、XXL、XXXL 等；普通数字、数量、单价、小计默认不要当尺码。
10. corrected_result 必须是完整 JSON，不要只输出变化字段。
11. 输出必须是严格 JSON，不要输出解释文字。
12. 如果规则错误指出 merchant_name 缺失，必须优先回看 OCR 顶部标题、店铺名称、商户名称；例如“XXX销售单”通常表示商家/店铺为“XXX”。
13. 如果规则错误或 warnings 指出商品名称缺失，必须回看同一商品行的款号附近 OCR 文本。服装票据常把款号、商品名、颜色粘在同一个文字块中，例如“307,湛蓝弹力小脚裤黑色”“20806上衣米白”，需要拆出商品名称，不要只保留款号。
14. 如果规则错误指出尺码非法，必须修正 size 和 sizes：size 只能是概括性尺码描述，例如均码、小、中、大、S、M、L、XL、XXL、XXXL 等；数字、数量、单价、小计、"S:3,M:2" 这类尺码数量明细不能放在 size 字段。
15. 当 OCR 表格有 S/M/L/XL 等尺码列及对应数量时，应把它们放入 sizes 数组，size 字段填 null 或明确主尺码；当表头是“均码”时，size 填“均码”，该列数字是数量。
16. OCR block 的 top/left 坐标可能有误差，颜色、尺码数量、数量、单价、小计可能发生上下错位。遇到规则错误时，不要只局部修一个字段，应回到 OCR 和第一轮结果，重建整张商品表。
17. 重建表格时，优先选择能同时满足行金额、尺码数量合计、总数量、总金额的整体解释。如果无法唯一确定，保留 unresolved_errors 并设置 need_review=true。

业务规则，全部条件触发：
R001：行数量 × 单价 = 行小计
R002：尺码数量之和 = 行数量
R003：所有行数量之和 = 总数量
R004：所有行小计之和 = 总金额
R005：支付金额之和 = 收款金额
R006：本次欠款 = 应收金额 - 收款金额
R007：累计欠款 = 上次欠款 + 本次欠款

只有字段存在时才使用对应规则；字段不存在不是错误。

请输出 JSON：
{
  "corrected_result": {},
  "corrections": [],
  "unresolved_errors": [],
  "need_review": false,
  "review_reason": null
}

OCR 原始结果：
{{OCR_RESULT}}

第一轮结构化 JSON：
{{RAW_STRUCTURED_JSON}}

规则引擎校验错误：
{{VALIDATION_ERRORS}}
"""


def get_second_round_prompt() -> str:
    return SECOND_ROUND_PROMPT.strip()


def render_second_round_prompt(
    ocr_json: dict[str, Any],
    structured_json: dict[str, Any],
    validation_errors: list[dict[str, Any]],
) -> str:
    replacements = {
        "{{OCR_RESULT}}": json.dumps(ocr_json, ensure_ascii=False, indent=2),
        "{{RAW_STRUCTURED_JSON}}": json.dumps(structured_json, ensure_ascii=False, indent=2),
        "{{VALIDATION_ERRORS}}": json.dumps(validation_errors, ensure_ascii=False, indent=2),
    }
    prompt = get_second_round_prompt()
    for placeholder, value in replacements.items():
        prompt = prompt.replace(placeholder, value)
    return prompt
