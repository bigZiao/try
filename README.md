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

## 作为 Codex Skill 使用

仓库内置了一个通用 Skill：

```text
skills/deepseek-research-agent
```

别人下载后可以把这个目录复制到自己的 Codex skills 目录，例如：

```text
C:\Users\他的用户名\.codex\skills\deepseek-research-agent
```

然后在自己的 `.env` 中配置：

```env
DEEPSEEK_API_KEY=他的_deepseek_key
DEEPSEEK_MODEL=deepseek-v4-pro
```

如果 Agent 项目不在当前工作目录，可以额外配置：

```env
DEEPSEEK_RESEARCH_AGENT_DIR=他的_agent_项目路径
```

之后可以在 Codex 里说：

```text
Use $deepseek-research-agent to research: 你的研究问题
```

## 作为 Codex Plugin 安装

仓库也内置了一个本地插件：

```text
plugins/deepseek-research-agent
```

如果对方的 Codex 支持从本地 marketplace 导入插件，可以使用：

```text
.agents/plugins/marketplace.json
```

其中插件入口指向：

```text
./plugins/deepseek-research-agent
```

安装后，插件会提供同名 Skill：

```text
deepseek-research-agent
```

使用前仍需要在 Agent 项目中配置自己的 `.env`：

```env
DEEPSEEK_API_KEY=他的_deepseek_key
DEEPSEEK_MODEL=deepseek-v4-pro
```
