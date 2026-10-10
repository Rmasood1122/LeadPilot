#!/usr/bin/env python3
"""Find credentials in lines a change ADDS (not in the whole history).

Used by scripts/gate/quick_gate.py on `git diff -U0` output. Each pattern is
specific enough that a hit is almost certainly a real key. A line that holds a
deliberate fake (a test fixture) can opt out with the marker
`gate: allow-secret` in a comment on the same line; reviewers see the marker.

Usage: git diff -U0 origin/master | python3 scripts/gate/scan_secrets.py
Exit 0 = clean, 1 = findings printed.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass

ALLOW_MARKER = "gate: allow-secret"

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Anthropic API key", re.compile(r"sk-ant-(?:api|admin)\d{2}-[A-Za-z0-9_\-]{40,}")),
    ("OpenAI-style secret key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{40,}\b")),
    ("AWS access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("Stripe live secret key", re.compile(r"\b[rs]k_live_[0-9A-Za-z]{20,}\b")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[0-9A-Za-z\-]{20,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("Private key block", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----")),
    ("Database URL with password",
     # The local-host exclusion must match the WHOLE host: an earlier version
     # used `db\b`, which also excluded `db.example.com` (caught by the gate
     # sabotage proof, PR #53).
     re.compile(r"\b(?:postgres(?:ql)?|redis|rediss|mysql)://[^\s:/@]+:[^\s@/]{6,}@"
                r"(?!(?:localhost|127\.0\.0\.1|db|redis|postgres)(?:[:/\s'\"]|$))[^\s/]+")),
)


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    kind: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}: possible {self.kind}"


def scan_diff(diff_text: str) -> list[Finding]:
    """Scan only '+' lines of a unified diff (with -U0 line numbers)."""
    findings: list[Finding] = []
    current_file = "?"
    new_line = 0
    for raw in diff_text.splitlines():
        if raw.startswith("+++ "):
            path = raw[4:].strip()
            current_file = path[2:] if path.startswith("b/") else path
            continue
        if raw.startswith("@@"):
            match = re.search(r"\+(\d+)", raw)
            new_line = int(match.group(1)) if match else 0
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            text = raw[1:]
            if ALLOW_MARKER not in text:
                for kind, pattern in PATTERNS:
                    if pattern.search(text):
                        findings.append(Finding(current_file, new_line, kind))
                        break
            new_line += 1
    return findings


def main() -> int:
    findings = scan_diff(sys.stdin.read())
    for finding in findings:
        print(finding)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
