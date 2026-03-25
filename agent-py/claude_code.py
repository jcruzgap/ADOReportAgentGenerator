import os
import subprocess
import sys


def _claude_cmd() -> str:
    """Return the correct claude executable name for the current platform."""
    if sys.platform == "win32":
        return "claude.cmd"
    return "claude"


def invoke_claude_code(
    prompt: str,
    working_dir: str,
    max_turns: int = 10,
) -> str:
    result = subprocess.run(
        [
            _claude_cmd(),
            "--print",
            "--dangerously-skip-permissions",
            "--max-turns", str(max_turns),
        ],
        input=prompt,
        cwd=working_dir,
        capture_output=True,
        text=True,
        timeout=900,  # 15 min timeout
    )

    if result.stderr:
        print(f"[claude-code stderr] {result.stderr[:500]}")

    if result.returncode != 0:
        raise RuntimeError(
            f"Claude Code exited with code {result.returncode}: {result.stderr[:500]}"
        )

    return result.stdout
