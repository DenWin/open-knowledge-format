#!/usr/bin/env python3
"""Fail if vendored skill files differ from their canonical sources."""

from pathlib import Path

from generate_agents import claude, copilot
import json
from generate_copilot_plugin import PLUGIN_MANIFEST, SKILLS

ROOT = Path(__file__).resolve().parents[2]
CANONICAL = ROOT / "tools/okf_adoc_core"
SKILLS = ("okf-generate-adoc", "okf-consume-adoc")


def main() -> int:
    failures = []
    for skill in SKILLS:
        base = ROOT / "skills" / skill
        comparisons = (
            (CANONICAL / "profile.py", base / "scripts/okf_adoc_core.py"),
            (CANONICAL / "validateWithAdoc.py", base / "scripts/validateWithAdoc.py"),
            (CANONICAL / "scanWithAdoc.py", base / "scripts/scanWithAdoc.py"),
            (CANONICAL / "asciidoc-profile.md", base / "references/asciidoc-profile.md"),
            (ROOT / "skills/okf-generate/scripts/validate.py", base / "scripts/okf_validate_base.py"),
            (ROOT / "skills/okf-consume/scripts/scan.py", base / "scripts/okf_scan_base.py"),
        )
        for source, generated in comparisons:
            if not generated.is_file() or source.read_bytes() != generated.read_bytes():
                failures.append(f"{generated.relative_to(ROOT)} is out of sync with {source.relative_to(ROOT)}")
        sync_script = base / "scripts/syncAttributes.py"
        if skill == "okf-generate-adoc":
            if not sync_script.is_file() or sync_script.read_bytes() != (CANONICAL / "syncAttributes.py").read_bytes():
                failures.append(f"{sync_script.relative_to(ROOT)} is out of sync with the canonical synchronizer")
        elif sync_script.exists():
            failures.append(f"{sync_script.relative_to(ROOT)} must not be shipped in the read-only consume skill")
    claude_agent = ROOT / "skills/agents/okf-adoption.md"
    expected_agent = claude((CANONICAL / "okf-adoption.agent.md").read_text(encoding="utf-8"))
    if not claude_agent.is_file() or claude_agent.read_text(encoding="utf-8") != expected_agent:
        failures.append("skills/agents/okf-adoption.md is out of sync with the canonical agent")
    copilot_agent = ROOT / ".github/agents/okf-adoption.agent.md"
    expected_agent = copilot((CANONICAL / "okf-adoption.agent.md").read_text(encoding="utf-8"))
    if not copilot_agent.is_file() or copilot_agent.read_text(encoding="utf-8") != expected_agent:
        failures.append(".github/agents/okf-adoption.agent.md is out of sync with the canonical agent")
    plugin_manifest = ROOT / "plugins/okf/plugin.json"
    if not plugin_manifest.is_file() or json.loads(plugin_manifest.read_text(encoding="utf-8")) != PLUGIN_MANIFEST:
        failures.append("plugins/okf/plugin.json is out of sync with the Copilot plugin manifest")
    for skill in SKILLS:
        source = ROOT / "skills" / skill
        bundled = ROOT / "plugins/okf/skills" / skill
        if not bundled.is_dir():
            failures.append(f"plugins/okf/skills/{skill} is missing")
            continue
        source_files = {
            p.relative_to(source)
            for p in source.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and p.suffix not in {".pyc", ".pyo"}
        }
        bundled_files = {p.relative_to(bundled) for p in bundled.rglob("*") if p.is_file()}
        if source_files != bundled_files:
            failures.append(f"plugins/okf/skills/{skill} file set differs from skills/{skill}")
        for relative in source_files & bundled_files:
            if (source / relative).read_bytes() != (bundled / relative).read_bytes():
                failures.append(f"plugins/okf/skills/{skill}/{relative} differs from skills/{skill}/{relative}")
    bundled_agent = ROOT / "plugins/okf/com.github.copilot/agents/okf-adoption.agent.md"
    if not bundled_agent.is_file() or not copilot_agent.is_file() or bundled_agent.read_bytes() != copilot_agent.read_bytes():
        failures.append("Copilot plugin agent differs from .github/agents/okf-adoption.agent.md")
    marketplace = ROOT / ".github/plugin/marketplace.json"
    if marketplace.is_file():
        catalog = json.loads(marketplace.read_text(encoding="utf-8"))
        entry = next((item for item in catalog.get("plugins", []) if item.get("name") == "okf"), None)
        if not entry or entry.get("source") != "plugins/okf":
            failures.append(".github/plugin/marketplace.json must publish the local plugins/okf bundle")
    else:
        failures.append(".github/plugin/marketplace.json is missing")
    if failures:
        print("\n".join(failures))
        return 1
    print("Generated skills and agent files match canonical sources.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
