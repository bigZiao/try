import json
from typing import Any


FIRST_ROUND_PROMPT = """
你是专业的服装批发票据解析专家。

下面是票据图片的 OCR 识别结果，包含文字块、坐标和置信度。OCR 可能存在粘连、拆分、错字、漏字、坐标误差。

你的任务是根据 OCR 文本、坐标关系、表格结构和金额数量关系，解析票据信息，并输出严格 JSON。

解析原则：

1. 只能基于 OCR 内容、坐标关系、表格结构和金额数量关系做合理解析，不允许编造 OCR 或图片中没有依据的信息。
2. 合理推断必须有证据，证据可以来自 OCR 文本、坐标列关系、相邻行结构、表头含义、数量金额计算关系。
3. 不能仅为了让规则成立而创造款号、商品名、颜色、尺码、数量、单价或金额。

4. parse_status 只能是 success / partial / failed。
5. need_review 只能是 true / false。
6. 如果票据主体和商品明细基本可靠，parse_status="success", need_review=false。
7. 如果能解析出票据和商品，但存在关键字段不确定、字段错位、多种解释、商品行冲突，parse_status="partial", need_review=true。
8. 如果无法可靠识别出票据主体或有效商品行，parse_status="failed", need_review=true。

9. 商品表格需要根据表头和坐标重建，重点识别关键字段：款号 style_no、商品名称 product_name、颜色 color、尺码 size/sizes、数量 quantity、单价 unit_price、金额 subtotal。
10. 每个商品行 style_no 和 product_name 至少应有一个。如果两者都没有可靠 OCR 证据，不要编造；如果该行数量/单价/金额明显存在但款号和商品名缺失，则保留该行，style_no=null, product_name=null, parse_status="partial", need_review=true。
11. 每个商品行 quantity、unit_price、subtotal 是必有字段，必须尽量解析。如果某行能确定是商品行但这三者任一无法确定，缺失字段填 null，parse_status="partial", need_review=true，并在 warnings 说明。
12. color 和 size/sizes 不是所有票据都有。只有表头、列内容或商品文本中出现颜色/尺码证据时才填写；如果票据本身没有颜色或尺码，不要因为缺失 color/size 而设置 parse_status="partial"。
13. 款号、商品名称、颜色、尺码、数量、单价、金额如果出现不合理、上下错位或无法唯一确定，设置 parse_status="partial", need_review=true，并在 warnings 说明。

14. OCR 可能把多个字段识别到一个文字块，也可能把一个字段拆成多个文字块，需要结合坐标和语义拆分或合并。
15. 第一轮可以做合理结构化推断，但不要为了让金额或数量成立而强行修改 OCR 数字。
16. 以下关系是强校验关系：行数量 × 单价 = 行金额；尺码数量之和 = 行数量；所有行金额之和 = 总金额。合理推断后如果仍不能满足，设置 parse_status="partial", need_review=true，并在 warnings 说明。
17. 金额全部输出数字，不要输出 ￥、¥、逗号。数量输出整数；无法确定时填 null。

18. 底部地址、电话、银行账号、二维码、打印程序、温馨提示等不要误当成商品或支付信息。
19. 只有带本单金额的支付宝、微信、现金、银行、汇款等文本，才识别为实际支付记录。
20. “款数”不是“数量”，“本次欠款”不是“收款金额”。

21. 本业务的单尺码描述通常是概括性尺码，例如均码、小、中、大、S、M、L、XL、XXL、XXXL 等；普通数字、数量、单价、金额默认不要当尺码。
22. 如果表格按 S/M/L/XL 等尺码列给出数量，例如 S=4、M=4、L=2，则 size 填 null，尺码数量明细放入 sizes，例如 [{"size_name":"S","quantity":4}]。不要输出 "S 4, M 4, L 2" 作为 size。
23. 如果表头是“均码”并且该列下面是数量数字，例如 5，则 size="均码", quantity=5，不能把 5 当作 size。

24. merchant_name 是必填业务字段。优先从票据顶部标题、店铺名称、商户名称中提取；例如“XXX销售单”通常表示商家/店铺为“XXX”。如果 OCR 中确实没有商家名称，merchant_name=null, parse_status="partial", need_review=true。
25. 服装票据常把款号、商品名、颜色粘在一个文字块中，例如“307,湛蓝弹力小脚裤黑色”“20806上衣米白”。需要根据逗号、空格、字母数字款号前缀、颜色词、坐标列关系拆分。
26. 如果同一商品行 OCR 中存在款号后紧跟中文文本，通常中文文本前半部分是商品名称，末尾颜色词可能是颜色。常见颜色词包括黑色、白色、米白、杏色、黄色、浅蓝、粉红、橘色、陶瓷绿、奶油绿、水绿色、姜黄等。

27. OCR block 的 top/left 坐标可能有误差，尤其是拍照小票、纸张弯曲、表格密集时。不要只按最近坐标归属字段，要结合表头、整行模式、相邻行重复结构、数量合计和金额合计综合判断。
28. 颜色、尺码数量、数量、单价、金额可能发生上下错位。遇到某一列字段和相邻行冲突时，不要局部硬塞字段，应尝试重建整张商品表。
29. 重建商品表时，优先选择能同时满足强校验关系的整体解释。
30. 如果存在多个整体解释都可能成立，或者 OCR 证据不足以判断字段属于上一行还是下一行，不要强行选择，设置 parse_status="partial", need_review=true，并在 warnings 中说明冲突点。

31. 每个重要字段尽量保留对应 OCR block_indexes。
32. 输出必须是严格 JSON，不要输出解释文字。

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
