#!/usr/bin/env python3
"""Fail if vendored skill files differ from their canonical sources."""

from pathlib import Path

from generate_agents import claude

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
    if failures:
        print("\n".join(failures))
        return 1
    print("Generated AsciiDoc skills match canonical sources.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
