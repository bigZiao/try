# 最小版 DeepSeek Research Agent

这是一个单文件 Python 版研究 Agent。它不调用 Tavily 或其他搜索服务，只使用 DeepSeek 的 OpenAI 兼容接口生成研究角度、证据卡片和 Markdown 研究报告。

> 注意：当前版本不做实时联网搜索，报告中的来源是“建议核验来源”。如果 URL 显示为 `N/A`，表示没有实时检索到网页，需要人工核验。

## 功能

- 根据问题生成研究角度
- 调用 DeepSeek 生成证据卡片
- 生成固定结构的 Markdown 研究报告
- 保存到 `outputs/report.md`

## 环境要求

- Python 3.10+
- DeepSeek API Key

## 安装依赖

```bash
pip install -r requirements.txt
```

## 配置环境变量

在项目根目录创建 `.env`：

```env
DEEPSEEK_API_KEY=你的_deepseek_key
DEEPSEEK_MODEL=deepseek-v4-pro
```

如果你的 DeepSeek 控制台给出的 V4 Pro 模型名不同，请把 `DEEPSEEK_MODEL` 改成控制台显示的实际模型 ID。

## 运行

```bash
python main.py "用户的研究问题"
```

示例：

```bash
python main.py "AI Agent 在企业知识库场景是否值得落地？"
```

运行完成后，报告会保存到：

```text
outputs/report.md
```

## 报告结构

生成的报告包含：

- 一句话结论
- 核心判断
- 关键证据
- 反方观点
- 不确定性
- 后续跟踪指标
- 来源列表

每条关键证据都会包含来源标题、URL、摘要和可信度评分。
