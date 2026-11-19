#!/usr/bin/env python3
"""Reconcile AsciiDoc header attributes from canonical OKF frontmatter.

Scope is one `.adoc` concept file or every `.adoc` file beneath a bundle root.
`--check` and `--dry-run` never write. Only `--write` modifies files.
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path

try:
    from okf_adoc_core import discover, split_frontmatter, sync_attributes
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from okf_adoc_core import discover, split_frontmatter, sync_attributes


def read_text(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return stream.read()


def get_files(target: Path) -> tuple[Path, list[Path]]:
    if target.is_symlink():
        raise ValueError(f"{target} is a symlink; refusing to synchronize through it")
    resolved = target.resolve()
    if resolved.is_file():
        return resolved.parent, [resolved]
    if not resolved.is_dir():
        raise ValueError(f"{target} is not a file or directory")
    files = sorted(path for path in resolved.rglob("*.adoc") if path.is_file() and not path.is_symlink())
    return resolved, files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path, help="an AsciiDoc concept or bundle root")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true", help="read-only consistency check")
    modes.add_argument("--dry-run", action="store_true", help="print proposed diffs without writing")
    modes.add_argument("--write", action="store_true", help="reconcile managed attributes")
    parser.add_argument("--mapping", action="append", default=[], metavar="YAML_KEY=ATTRIBUTE",
                        help="add or override an explicit mapping to an okf-* attribute")
    parser.add_argument("--value-mapping", action="append", default=[], metavar="YAML_KEY=FROM:TO",
                        help="explicitly map a legacy scalar value, such as status=accepted:stable")
    args = parser.parse_args(argv)
    try:
        root, files = get_files(args.target)
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 2
    mappings = {}
    for entry in args.mapping:
        if "=" not in entry:
            parser.error("--mapping must be YAML_KEY=ATTRIBUTE")
        key, value = entry.split("=", 1)
        mappings[key] = value
    value_mappings: dict[str, dict[str, str]] = {}
    for entry in args.value_mapping:
        if "=" not in entry or ":" not in entry.split("=", 1)[1]:
            parser.error("--value-mapping must be YAML_KEY=FROM:TO")
        key, mapping = entry.split("=", 1)
        old, new = mapping.split(":", 1)
        value_mappings.setdefault(key, {})[old] = new
    _, collisions = discover(root)
    collision_paths = {path for paths in collisions.values() for path in paths}
    results = []
    failed = False
    for path in files:
        if path.is_symlink():
            continue
        try:
            path.resolve().relative_to(root)
        except ValueError:
            results.append({"path": str(path), "state": "unsupported",
                            "diagnostics": [{"code": "path-escape", "message": "file is outside bundle root"}]})
            failed = True
            continue
        relative = path.relative_to(root).as_posix()
        if relative in collision_paths:
            results.append({
                "path": relative,
                "state": "conflict",
                "diagnostics": [{
                    "code": "identity-collision",
                    "message": f"concept ID is ambiguous: {', '.join(next(paths for paths in collisions.values() if relative in paths))}",
                }],
            })
            failed = True
            continue
        try:
            text = read_text(path)
        except (OSError, UnicodeError) as exc:
            results.append({
                "path": relative,
                "state": "unsupported",
                "diagnostics": [{"code": "read-error", "message": str(exc)}],
            })
            failed = True
            continue
        metadata, _, error, _ = split_frontmatter(text)
        if error == "frontmatter is absent":
            results.append({"path": relative, "state": "not_applicable", "diagnostics": []})
            continue
        if error:
            results.append({"path": relative, "state": "unsupported",
                            "diagnostics": [{"code": "frontmatter-error", "message": error}]})
            failed = True
            continue
        identifier = path.relative_to(root).as_posix()
        if identifier.endswith(".adoc"):
            identifier = identifier
        plan = sync_attributes(
            text,
            metadata,
            identifier,
            write=args.write or args.dry_run,
            mappings=mappings,
            value_mappings=value_mappings,
        )
        result = {
            "path": relative,
            "state": plan.state,
            "diagnostics": [finding.__dict__ for finding in plan.findings],
        }
        if args.dry_run and plan.updated_text is not None and plan.updated_text != text:
            result["diff"] = "".join(difflib.unified_diff(
                text.splitlines(keepends=True),
                plan.updated_text.splitlines(keepends=True),
                fromfile=str(path),
                tofile=str(path) + " (proposed)",
            ))
        if args.write and plan.updated_text is not None and plan.updated_text != text:
            try:
                with path.open("w", encoding="utf-8", newline="") as stream:
                    stream.write(plan.updated_text)
                result["written"] = True
            except OSError as exc:
                result["state"] = "unsupported"
                result["diagnostics"].append({"code": "write-error", "message": str(exc)})
                failed = True
        results.append(result)
        if args.check:
            failed |= plan.state not in ("ok", "not_applicable")
        if args.write:
            failed |= plan.state in ("unsupported", "conflict")
    print(json.dumps({"files": results}, ensure_ascii=False, indent=2))
    return 1 if failed and args.check else (2 if failed and args.write else 0)


if __name__ == "__main__":
    sys.exit(main())
