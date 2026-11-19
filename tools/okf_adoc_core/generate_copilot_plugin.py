#!/usr/bin/env python3
"""Build the Copilot Agent Plugin from the canonical skills and adoption agent."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins/okf"
SKILLS = ("okf-generate", "okf-consume", "okf-generate-adoc", "okf-consume-adoc")
PLUGIN_MANIFEST = {
    "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
    "name": "okf",
    "version": "0.1.0",
    "description": (
        "Open Knowledge Format skills for standard Markdown bundles and the "
        "opt-in okf-adoc/1.0 profile, with adoption guidance."
    ),
    "author": {"name": "Open Knowledge Format contributors"},
    "homepage": "https://github.com/open-knowledge-format/open-knowledge-format",
    "repository": "https://github.com/open-knowledge-format/open-knowledge-format",
    "license": "Apache-2.0",
    "keywords": ["okf", "open-knowledge-format", "knowledge", "agent-skills"],
}


def main() -> None:
    skills_dir = PLUGIN / "skills"
    if skills_dir.exists():
        shutil.rmtree(skills_dir)
    skills_dir.mkdir(parents=True)
    for skill in SKILLS:
        shutil.copytree(
            ROOT / "skills" / skill,
            skills_dir / skill,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
    manifest = PLUGIN / "plugin.json"
    manifest.write_text(json.dumps(PLUGIN_MANIFEST, indent=2) + "\n", encoding="utf-8")
    agent_dir = PLUGIN / "com.github.copilot/agents"
    agent_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        ROOT / ".github/agents/okf-adoption.agent.md",
        agent_dir / "okf-adoption.agent.md",
    )


if __name__ == "__main__":
    main()
