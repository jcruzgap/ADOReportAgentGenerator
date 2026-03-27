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
    # Encode prompt explicitly to UTF-8 bytes to avoid Windows charmap issues
    result = subprocess.run(
        [
            _claude_cmd(),
            "--print",
            "--dangerously-skip-permissions",
            "--max-turns", str(max_turns),
        ],
        input=prompt.encode("utf-8"),
        cwd=working_dir,
        capture_output=True,
        timeout=1800,  # 30 min timeout
    )

    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")

    if stderr:
        print(f"[claude-code stderr] {stderr[:1000]}")

    if result.returncode != 0:
        detail = (stderr or stdout or "(no output)")[:1000]
        raise RuntimeError(
            f"Claude Code exited with code {result.returncode}: {detail}"
        )

    return stdout
