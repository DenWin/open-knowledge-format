#!/usr/bin/env python3
"""Generate target-specific agent frontmatter from one canonical instruction body."""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tools/okf_adoc_core/okf-adoption.agent.md"


def body(source: str) -> str:
    parts = source.split("---", 2)
    if len(parts) != 3:
        raise ValueError("canonical agent must have a YAML frontmatter block")
    return parts[2].lstrip("\r\n")


def copilot(source: str) -> str:
    return (
        "---\nname: okf-adoption\n"
        "description: Plan and safely adopt, migrate, or maintain repositories as OKF v0.3 or the opt-in okf-adoc/1.0 profile.\n"
        "tools: [read, edit, search, agent]\n"
        "---\n\n" + body(source)
    )


def claude(source: str) -> str:
    return (
        "---\nname: okf-adoption\n"
        "description: Plan and safely adopt, migrate, or maintain repositories as OKF v0.3 or the opt-in okf-adoc/1.0 profile.\n"
        "tools: Read, Edit, Glob, Grep, Skill\n"
        "---\n\n" + body(source)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("claude", "copilot", "all"), default="all")
    args = parser.parse_args()
    text = SOURCE.read_text(encoding="utf-8")
    if args.target in ("claude", "all"):
        destination = ROOT / "skills/agents/okf-adoption.md"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(claude(text), encoding="utf-8")
    if args.target in ("copilot", "all"):
        destination = ROOT / ".github/agents/okf-adoption.agent.md"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(copilot(text), encoding="utf-8")


if __name__ == "__main__":
    main()
