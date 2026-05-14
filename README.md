# 最小版 Deep Research Agent

这是一个单文件 Python 版 Deep Research Agent。它接收一个研究问题，自动生成搜索词，调用 Tavily 搜索，整理搜索结果，再用 DeepSeek 的 OpenAI 兼容接口提取证据卡片并生成 Markdown 研究报告。

## 功能

- 生成搜索词
- 调用 Tavily 搜索
- 整理和去重搜索结果
- 调用 DeepSeek 提取证据卡片
- 生成固定结构的 Markdown 研究报告
- 保存到 `outputs/report.md`

## 环境要求

- Python 3.10+
- DeepSeek API Key
- Tavily API Key

## 安装依赖

```bash
pip install -r requirements.txt
```

## 配置环境变量

在项目根目录创建 `.env`：

```env
DEEPSEEK_API_KEY=你的_deepseek_key
TAVILY_API_KEY=你的_tavily_key
DEEPSEEK_MODEL=deepseek-chat
```

如果你已经把 DeepSeek Key 临时放在 `OPENAI_API_KEY` 中，程序也会把它作为兼容回退读取。不过推荐使用 `DEEPSEEK_API_KEY`。

## 运行

```bash
python main.py "用户的研究问题"
```

示例：

```bash
python main.py "2026 年中国新能源汽车出口增长是否可持续？"
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
