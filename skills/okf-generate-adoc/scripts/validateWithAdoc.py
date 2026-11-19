#!/usr/bin/env python3
"""Read-only validator for Markdown and AsciiDoc OKF v0.3 profile bundles."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

try:
    from okf_adoc_core import PROFILE, discover, resolve_target, split_frontmatter, sync_attributes, targets
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from okf_adoc_core import PROFILE, discover, resolve_target, split_frontmatter, sync_attributes, targets

SOURCE_FOOTNOTE_RE = re.compile(r"(?<!\\)\bfootnote:([A-Za-z0-9_.-]+)\[")
FOOTNOTEREF_RE = re.compile(r"(?<!\\)\bfootnoteref:\[([^\]]+)\]")


def load_base() -> object:
    here = Path(__file__).resolve().parent
    candidate = here / "okf_validate_base.py"
    if not candidate.is_file():
        candidate = here.parents[1] / "skills/okf-generate/scripts/validate.py"
    spec = importlib.util.spec_from_file_location("okf_validate_base", candidate)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load baseline validator: {candidate}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def asciidoc_computation_blocks(body: str) -> int:
    section = False
    level = None
    blocks = 0
    in_block = False
    for line in body.splitlines():
        heading = re.match(r"^(={2,6})\s+(.+?)\s*$", line)
        if heading:
            depth = len(heading.group(1))
            if level is not None and depth <= level:
                section, level = False, None
            if heading.group(2).strip().casefold() == "computation":
                section, level = True, depth
            continue
        if section and line.strip() == "----":
            if not in_block:
                blocks += 1
            in_block = not in_block
    return blocks


def find_target(root: Path, source: Path, target: str) -> Path | None:
    candidate = resolve_target(root, source, target)
    if candidate is None:
        return None
    if candidate.is_file():
        return candidate
    if not candidate.suffix:
        matches = [Path(str(candidate) + ext) for ext in (".adoc", ".md")]
        found = [item for item in matches if item.is_file()]
        return found[0] if len(found) == 1 else None
    return None


def check_footnotes(checker: object, path: Path, body: str, body_line: int, source_ids: set[str]) -> None:
    declared = set()
    references = []
    for offset, line in enumerate(body.splitlines()):
        number = body_line + offset
        for match in SOURCE_FOOTNOTE_RE.finditer(line):
            source_id = match.group(1)
            declared.add(source_id)
            if source_id not in source_ids:
                checker.warn(path, number, "A120", f"AsciiDoc footnote source ID {source_id!r} has no sources entry")
        references.extend((match.group(1), number) for match in FOOTNOTEREF_RE.finditer(line))
    for identifier, number in references:
        if identifier not in declared:
            checker.warn(path, number, "A121", f"footnoteref {identifier!r} has no preceding footnote definition")


def add_adoc_findings(checker: object, root: Path, base: object) -> None:
    concepts, collisions = discover(root)
    all_adoc = []
    for candidate in sorted(root.rglob("*.adoc")):
        relative = candidate.relative_to(root)
        if candidate.is_symlink() or any(part.startswith(".") for part in relative.parts) or not candidate.is_file():
            continue
        try:
            candidate.resolve().relative_to(root)
        except ValueError:
            continue
        all_adoc.append(candidate)
    for identifier, paths in collisions.items():
        checker.error(root, None, "E130", f"ambiguous concept ID {identifier!r} exists at: {', '.join(paths)}")
    concept_paths = {item.path.resolve() for item in concepts if item.format == "asciidoc" and item.metadata.get("type")}
    discovered_paths = {item.path.resolve() for item in concepts if item.format == "asciidoc"}
    included_partials = set()
    for candidate in all_adoc:
        _, candidate_body, _, _ = split_frontmatter(candidate.read_text(encoding="utf-8"))
        for kind, target, _ in targets(candidate_body):
            if kind == "include":
                resolved = resolve_target(root, candidate, target)
                if resolved is not None:
                    included_partials.add(resolved)
    for item in concepts:
        if item.format != "asciidoc":
            continue
        path = item.path
        checker.files_checked += 1
        text = path.read_text(encoding="utf-8")
        state, metadata, body, body_line = checker.frontmatter(path, text.lstrip(base.BOM))
        if state == "absent":
            checker.warn(path, 1, "W120", "not a concept: the file has no frontmatter (section 3.2)")
            continue
        if state != "ok":
            continue
        concept_type = metadata.get("type")
        if not isinstance(concept_type, str) or not concept_type.strip():
            checker.warn(path, 1, "W120", "not a concept: the frontmatter has no non-empty type")
            continue
        checker.check_strings(path, metadata)
        checker.check_tags(path, metadata)
        checker.check_lifecycle(path, metadata)
        generated_at = checker.check_generated(path, metadata)
        checker.check_verified(path, metadata, generated_at)
        source_ids = checker.check_sources(path, metadata)
        checker.check_stale_after(path, metadata)
        for field in ("resource", "superseded_by", "computation"):
            if not base.blank(metadata.get(field)):
                checker.check_path_field(path, field, metadata[field])
        if concept_type == "Attested Computation":
            if base.blank(metadata.get("runtime")):
                checker.warn(path, 1, "W111", "an Attested Computation needs runtime (section 10.2)")
            count = asciidoc_computation_blocks(body)
            if base.blank(metadata.get("computation")) and count == 0:
                checker.warn(path, body_line, "W112", "no computation: no computation field and no source block in a Computation section")
            elif base.blank(metadata.get("computation")) and count > 1:
                checker.warn(path, body_line, "W112", f"put exactly one source block in the Computation section; found {count}")
            elif not base.blank(metadata.get("computation")) and count:
                checker.warn(path, body_line, "W112", "with a computation field, do not also put a source block in the Computation section")
            for index, parameter in enumerate(base.as_list(metadata.get("parameters"))):
                if not isinstance(parameter, dict) or base.blank(parameter.get("name")) or base.blank(parameter.get("type")):
                    checker.warn(path, 1, "W113", f"parameters[{index}] needs name and type (section 10.2)")
            for key in ("executor", "attester"):
                value = metadata.get(key)
                if base.blank(value):
                    continue
                if not isinstance(value, dict) or base.blank(value.get("resource")):
                    checker.warn(path, 1, "W114", f"{key} is a mapping with a resource field (section 10.2)")
                    continue
                if key == "executor" and not isinstance(value.get("receipt"), list):
                    checker.warn(path, 1, "W114", "executor.receipt lists the fields that a run returns (section 10.2)")
                checker.check_path_field(path, f"{key}.resource", value.get("resource"))
            if base.blank(metadata.get("attester")):
                checker.info(path, 1, "I205", "without an attester, consumers cannot show values from this computation as attested")
        check_footnotes(checker, path, body, body_line, source_ids)

        attribute_result = sync_attributes(text, metadata, item.concept_id)
        if attribute_result.state != "ok":
            level = "error" if attribute_result.state in ("conflict", "unsupported") else "warning"
            checker.add(path, 1, level, "A101", f"AsciiDoc attribute synchronization is {attribute_result.state}")
            for finding in attribute_result.findings:
                checker.add(path, finding.line or 1, finding.level, "A102", finding.message)

        unknown = sorted(
            str(key) for key in metadata
            if str(key) not in base.KNOWN_KEYS and not str(key).startswith("x-")
        )
        if unknown:
            checker.info(path, 1, "I203", f"extension keys without the x- prefix: {', '.join(unknown)} (section 4.1)")

        for kind, target, line in targets(body):
            if kind == "include":
                continue
            absolute_line = body_line + line - 1
            if kind in ("xref", "shorthand") and target.startswith("/"):
                checker.warn(path, absolute_line, "A110", f"root-relative xref {target!r} may render as a web-root URL; prefer a relative path")
            if kind == "xref" and target.startswith("#"):
                continue
            target_path_part = target.split("#", 1)[0]
            if kind == "shorthand" and not target.startswith("/") and "/" not in target_path_part and not target_path_part.endswith((".adoc", ".md")):
                continue
            external = re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target) or target.startswith("//")
            if external:
                continue
            resolved = resolve_target(root, path, target)
            if resolved is None:
                checker.warn(path, absolute_line, "A111", f"{kind} target {target!r} escapes the bundle or cannot be resolved")
                continue
            target_path = find_target(root, path, target)
            if target_path is None:
                checker.warn(path, absolute_line, "A112", f"{kind} target {target!r} is not in the bundle or is ambiguous")
                continue
    for path in all_adoc:
        resolved_source = path.resolve()
        if resolved_source in discovered_paths:
            text = path.read_text(encoding="utf-8")
            _, body, _, body_line = split_frontmatter(text)
        else:
            text = path.read_text(encoding="utf-8")
            _, body, _, body_line = split_frontmatter(text)
            if resolved_source not in included_partials:
                checker.files_checked += 1
                checker.warn(path, 1, "W120", "not a concept: the file has no OKF frontmatter (section 3.2)")
        for kind, target, line in targets(body):
            if kind != "include":
                continue
            absolute_line = body_line + line - 1
            external = re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target) or target.startswith("//")
            if external:
                checker.error(path, absolute_line, "A111", f"include target {target!r} is not a local bundle path")
                continue
            resolved = resolve_target(root, path, target)
            if resolved is None:
                checker.error(path, absolute_line, "A111", f"include target {target!r} escapes the bundle")
                continue
            target_path = find_target(root, path, target)
            if target_path is None:
                checker.warn(path, absolute_line, "A112", f"include target {target!r} is not in the bundle")
            elif target_path.resolve() in concept_paths:
                checker.error(path, absolute_line, "A113", f"include target {target!r} is a concept document; include partials only")


def main(argv: list[str] | None = None) -> int:
    base = load_base()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--now")
    args = parser.parse_args(argv)
    root = args.bundle.resolve()
    if not root.is_dir():
        print(f"validateWithAdoc.py: {args.bundle} is not a directory", file=sys.stderr)
        return 2
    now = datetime.now(timezone.utc)
    if args.now:
        now = base.parse_timestamp(args.now)
        if now is None:
            print("validateWithAdoc.py: --now must be an RFC 3339 date-time with an offset", file=sys.stderr)
            return 2
    checker = base.Checker(root, now)
    checker.run()
    add_adoc_findings(checker, root, base)
    counts = {level: sum(f.level == level for f in checker.findings) for level in ("error", "warning", "info")}
    if args.json:
        print(json.dumps({
            "bundle": str(root),
            "okf_version": checker.okf_version,
            "files_checked": checker.files_checked,
            "errors": counts["error"],
            "warnings": counts["warning"],
            "info": counts["info"],
            "findings": [base.asdict(f) for f in checker.findings],
        }, indent=2))
    else:
        for finding in checker.findings:
            location = f"{finding.path}:{finding.line}" if finding.line else finding.path
            print(f"{location}: {finding.level} {finding.code} {finding.message}")
        print(f"{checker.files_checked} files checked: {counts['error']} errors, {counts['warning']} warnings, {counts['info']} info.")
    return 1 if counts["error"] or (args.strict and counts["warning"]) else 0


if __name__ == "__main__":
    sys.exit(main())
