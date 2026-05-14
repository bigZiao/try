import argparse
import os
import subprocess
import sys
from pathlib import Path


def resolve_project_dir(project_dir: str | None) -> Path:
    """Resolve the local agent project directory without hard-coding a user path."""
    candidates: list[Path] = []

    if project_dir:
        candidates.append(Path(project_dir))

    env_dir = os.getenv("DEEPSEEK_RESEARCH_AGENT_DIR")
    if env_dir:
        candidates.append(Path(env_dir))

    candidates.append(Path.cwd())

    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if (resolved / "main.py").exists():
            return resolved

    searched = "\n".join(str(path) for path in candidates)
    raise FileNotFoundError(f"Cannot find agent project with main.py. Searched:\n{searched}")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the wrapper."""
    parser = argparse.ArgumentParser(description="Run the local DeepSeek research agent.")
    parser.add_argument("question", nargs="+", help="Research question to pass to main.py")
    parser.add_argument("--project-dir", help="Path to the local agent project directory")
    return parser.parse_args()


def main() -> int:
    """Run the local agent and print the generated report path."""
    args = parse_args()
    question = " ".join(args.question).strip()
    project_dir = resolve_project_dir(args.project_dir)
    report_path = project_dir / "outputs" / "report.md"

    if not (project_dir / ".env").exists():
        print(f"Missing .env file in {project_dir}", file=sys.stderr)
        return 1

    command = [sys.executable, "main.py", question]
    result = subprocess.run(command, cwd=project_dir, text=True)
    if result.returncode != 0:
        return result.returncode

    print(f"REPORT_PATH={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
