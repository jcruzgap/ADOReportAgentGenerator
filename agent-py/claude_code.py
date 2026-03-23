import os
import subprocess
import tempfile


def invoke_claude_code(
    prompt: str,
    working_dir: str,
    max_turns: int = 10,
) -> str:
    # Write prompt to a temp file to avoid shell escaping issues
    prompt_file = os.path.join(working_dir, ".agent-prompt.md")
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(prompt)

    try:
        result = subprocess.run(
            [
                "claude",
                "--print",
                "--dangerously-skip-permissions",
                "--max-turns", str(max_turns),
                "--input-file", prompt_file,
            ],
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=300,  # 5 min timeout
        )

        if result.stderr:
            print(f"[claude-code stderr] {result.stderr[:500]}")

        if result.returncode != 0:
            raise RuntimeError(
                f"Claude Code exited with code {result.returncode}: {result.stderr[:500]}"
            )

        return result.stdout
    finally:
        if os.path.exists(prompt_file):
            os.remove(prompt_file)
