import json
from typing import Any


FIRST_ROUND_PROMPT = """
你是专业的服装批发票据解析专家。

下面是票据图片的 OCR 识别结果，包含文字块、坐标和置信度。OCR 可能存在粘连、拆分、错字、漏字。

你的任务是根据 OCR 文本和坐标关系，解析票据信息，并输出严格 JSON。

解析原则：

1. 只能基于 OCR 内容和坐标关系解析，不允许编造。
2. 横向坐标接近的文字通常属于同一商品行，纵向坐标接近的文字通常属于同一列。
3. 商品表格需要根据表头和坐标重建，识别款号、商品名称、颜色、尺码、数量、单价、小计。
4. OCR 可能把多个字段识别到一个文字块里，也可能把一个字段拆成多个文字块，需要结合坐标和语义拆分或合并。
5. 第一轮只做结构化整理，不要为了让金额或数量成立而强行修改 OCR 数字。
6. 金额全部输出数字，不要输出 ￥、¥、逗号。
7. 数量输出整数。
8. 底部地址、电话、银行账号、二维码、打印程序、温馨提示等不要误当成商品或支付信息。
9. 只有带本单金额的支付宝、微信、现金、银行、汇款等文本，才识别为实际支付记录。
10. “款数”不是“数量”，“本次欠款”不是“收款金额”。
11. 本业务的单尺码描述通常是概括性尺码，例如均码、小、中、大、S、M、L、XL、XXL、XXXL 等；普通数字、数量、单价、小计默认不要当尺码。
12. 不确定的字段填 null，并在 warnings 中说明。
13. 每个重要字段尽量保留对应 OCR block_indexes。
14. 输出必须是严格 JSON，不要输出解释文字。
15. merchant_name 是必填业务字段。优先从票据顶部标题、店铺名称、商户名称中提取；例如“XXX销售单”通常表示商家/店铺为“XXX”。如果 OCR 中确实没有商家名称，填 null，并设置 need_review=true。
16. 每个商品都应尽量同时解析款号和商品名称。服装票据常把款号、商品名、颜色粘在一个文字块中，例如“307,湛蓝弹力小脚裤黑色”“20806上衣米白”。需要根据逗号、空格、字母数字款号前缀、颜色词、坐标列关系拆分，不能只保留款号而丢弃商品名称。
17. 如果同一商品行 OCR 中存在款号后紧跟中文文本，通常中文文本前半部分是商品名称，末尾颜色词是颜色。常见颜色词包括黑色、白色、米白、杏色、黄色、浅蓝、粉红、橘色、陶瓷绿、奶油绿、水绿色、姜黄等。
18. size 字段只能填写概括性尺码描述，例如均码、小、中、大、S、M、L、XL、XXL、XXXL 等。不要把数量数字、单价、小计、行号、尺码数量表达式填入 size。
19. 如果表格按 S/M/L/XL 等尺码列给出数量，例如 S=4、M=4、L=2，则 size 填 null 或主尺码无法确定，尺码数量明细放入 sizes，例如 [{"size_name":"S","quantity":4},{"size_name":"M","quantity":4},{"size_name":"L","quantity":2}]。不要输出 "S 4, M 4, L 2" 作为 size。
20. 如果表头是“均码”并且该列下面是数量数字，例如 5，则 size 应为“均码”，quantity 为 5，不能把 5 当作 size。
21. OCR block 的 top/left 坐标可能有误差，尤其是拍照小票、纸张弯曲、表格密集时。不要只按最近坐标归属字段，要结合表头、整行模式、相邻行重复结构、数量合计和金额合计综合判断。
22. 颜色、尺码数量、数量、单价、小计可能发生上下错位。遇到某一列字段和相邻行冲突时，不要局部硬塞字段，应尝试重建整张商品表。
23. 重建商品表时，优先选择能同时满足“行数量 × 单价 = 行小计”“尺码数量之和 = 行数量”“所有行小计之和 = 总金额”的整体解释。
24. 如果存在多个整体解释都可能成立，或者 OCR 证据不足以判断字段属于上一行还是下一行，不要强行选择，设置 need_review=true，并在 warnings 中说明冲突点。

请输出标准结构化 JSON，字段包括：
parse_status, bill_type, merchant_name, order_date, customer_name, customer_phone, order_no, salesperson, items, summary, payments, warnings, confidence, confidence_reason, need_review。

OCR结果：
{{OCR_RESULT}}
"""


def get_first_round_prompt() -> str:
    return FIRST_ROUND_PROMPT.strip()


def render_first_round_prompt(ocr_json: dict[str, Any]) -> str:
    ocr_text = json.dumps(ocr_json, ensure_ascii=False, indent=2)
    return get_first_round_prompt().replace("{{OCR_RESULT}}", ocr_text)
