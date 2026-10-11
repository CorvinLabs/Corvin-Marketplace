"""Lint test for subprocess.run and asyncio.create_subprocess_exec usage.

Deadline primitive (ADR-2247, PLAN-0946 R1b step 1) requires that any subprocess
call in the plugin source must either:
1. Respect the job's deadline (pass the job_id to a deadline-aware wrapper), or
2. Be explicitly marked with a `# deadline-exempt: <reason>` comment on the line
   where subprocess.run or create_subprocess_exec is called.

This test fails if any bare subprocess.run or create_subprocess_exec is found
without a deadline-exempt comment.
"""
import re
from pathlib import Path

import pytest


# Patterns to match subprocess.run or asyncio.create_subprocess_exec
SUBPROCESS_RUN_RE = re.compile(r'\bsubprocess\.run\b')
CREATE_SUBPROCESS_EXEC_RE = re.compile(r'\bcreate_subprocess_exec\b')
DEADLINE_EXEMPT_RE = re.compile(r'#\s*deadline-exempt:\s*(.+)$')


def _get_src_files():
    """Get all Python source files in src/ (not tests)."""
    src_dir = Path(__file__).parent.parent / "src"
    return sorted(src_dir.rglob("*.py"))


def _check_file(path: Path) -> list[tuple[int, str]]:
    """Check a single file for bare subprocess calls. Returns list of (line_no, issue)."""
    issues = []
    try:
        content = path.read_text()
    except Exception:
        return issues

    for line_no, line in enumerate(content.split('\n'), start=1):
        # Skip lines with deadline-exempt comment
        if DEADLINE_EXEMPT_RE.search(line):
            continue

        # Check for subprocess.run or create_subprocess_exec
        if SUBPROCESS_RUN_RE.search(line) or CREATE_SUBPROCESS_EXEC_RE.search(line):
            issues.append((line_no, f"Bare subprocess call without deadline-exempt comment: {line.strip()}"))

    return issues


class TestSubprocessDeadlineExemption:
    """Lint test that all subprocess calls are either deadline-aware or explicitly exempted."""

    def test_no_bare_subprocess_calls(self):
        """All subprocess.run or create_subprocess_exec calls must be deadline-aware or exempted."""
        all_issues = {}
        for src_file in _get_src_files():
            issues = _check_file(src_file)
            if issues:
                all_issues[src_file] = issues

        if all_issues:
            msg_lines = ["Found bare subprocess calls without deadline-exempt comments:\n"]
            for path, issues in sorted(all_issues.items()):
                msg_lines.append(f"\n{path.relative_to(path.parent.parent)}:")
                for line_no, issue in issues:
                    msg_lines.append(f"  Line {line_no}: {issue}")
            pytest.fail("\n".join(msg_lines))
