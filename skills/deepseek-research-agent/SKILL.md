---
name: deepseek-research-agent
description: Run a local DeepSeek-only research agent for research questions, generating a Markdown report through the bundled wrapper script. Use when the user asks to use their research agent, DeepSeek research agent, deep research agent, or wants a saved Markdown research report without Tavily/search.
---

# DeepSeek Research Agent

## Workflow

Use this skill when the user wants to run a local DeepSeek-only research agent.

1. Locate the agent project directory. Prefer, in order:
   - A `--project-dir` argument supplied to `scripts/run_research_agent.py`
   - The `DEEPSEEK_RESEARCH_AGENT_DIR` environment variable
   - The current working directory, if it contains `main.py`
2. Confirm the project has `main.py`, `requirements.txt`, and `.env`.
3. Do not print `.env` contents or secrets.
4. Run:

```bash
python scripts/run_research_agent.py "research question" --project-dir "path/to/agent/project"
```

5. After the script finishes, read the `REPORT_PATH=...` line printed by the wrapper and summarize that Markdown report for the user.

## Notes

- This agent does not call Tavily or any search engine.
- The report's sources are suggested verification sources, not live web results.
- If dependencies are missing, run `pip install -r requirements.txt` in the project directory.
- If DeepSeek returns a model-name error, tell the user to set `DEEPSEEK_MODEL` in `.env` to the exact model ID shown in their DeepSeek console.
- Do not commit or display `.env`.
