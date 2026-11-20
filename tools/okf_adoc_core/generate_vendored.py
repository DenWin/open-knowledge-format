#!/usr/bin/env python3
"""Regenerate the self-contained AsciiDoc skill payloads from canonical files."""

from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
CANONICAL = ROOT / "tools" / "okf_adoc_core"
SKILLS = (
    ROOT / "skills" / "okf-generate-adoc",
    ROOT / "skills" / "okf-consume-adoc",
)


def main() -> None:
    for skill in SKILLS:
        scripts = skill / "scripts"
        references = skill / "references"
        scripts.mkdir(parents=True, exist_ok=True)
        references.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CANONICAL / "profile.py", scripts / "okf_adoc_core.py")
        if skill.name == "okf-generate-adoc":
            shutil.copyfile(CANONICAL / "syncAttributes.py", scripts / "syncAttributes.py")
        else:
            (scripts / "syncAttributes.py").unlink(missing_ok=True)
        shutil.copyfile(CANONICAL / "validateWithAdoc.py", scripts / "validateWithAdoc.py")
        shutil.copyfile(CANONICAL / "scanWithAdoc.py", scripts / "scanWithAdoc.py")
        shutil.copyfile(CANONICAL / "asciidoc-profile.md", references / "asciidoc-profile.md")
        for source, output in (
            (ROOT / "skills" / "okf-generate" / "scripts" / "validate.py", scripts / "okf_validate_base.py"),
            (ROOT / "skills" / "okf-consume" / "scripts" / "scan.py", scripts / "okf_scan_base.py"),
        ):
            shutil.copyfile(source, output)


if __name__ == "__main__":
    main()
