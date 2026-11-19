#!/usr/bin/env python3
"""Read-only OKF scanner for Markdown and AsciiDoc profile bundles."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import urllib.parse

from okf_adoc_core import discover


def load_base() -> object:
    here = Path(__file__).resolve().parent
    candidate = here / "okf_scan_base.py"
    if not candidate.is_file():
        candidate = here.parents[1] / "skills/okf-consume/scripts/scan.py"
    spec = importlib.util.spec_from_file_location("okf_scan_base", candidate)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load baseline scanner: {candidate}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def bundle_with_adoc_paths(base: object, root: Path) -> object:
    class ExtendedBundle(base.Bundle):
        def concept_id(self, source: Path, target: object) -> str | None:
            if not isinstance(target, str) or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target):
                return None
            clean = urllib.parse.unquote(target.split("#", 1)[0].split("?", 1)[0])
            base_path = self.root if clean.startswith("/") else source.parent
            candidates = [Path(os.path.normpath(base_path / clean.lstrip("/")))]
            if not Path(clean).suffix:
                candidates.extend(Path(str(candidate) + ext) for candidate in tuple(candidates) for ext in (".md", ".adoc"))
            if self.root_fallback and not clean.startswith("/"):
                fallback = Path(os.path.normpath(self.root / clean))
                candidates.append(fallback)
                if not fallback.suffix:
                    candidates.extend(Path(str(fallback) + ext) for ext in (".md", ".adoc"))
            for candidate in candidates:
                try:
                    resolved = candidate.resolve()
                    resolved.relative_to(self.root)
                except ValueError:
                    continue
                if not resolved.is_file():
                    continue
                rel = resolved.relative_to(self.root).as_posix()
                if rel.endswith(".md"):
                    return rel[:-3]
                if rel.endswith(".adoc"):
                    return rel
            return None

    return ExtendedBundle(root)


def main(argv: list[str] | None = None) -> int:
    base = load_base()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--type")
    parser.add_argument("--tag")
    parser.add_argument("--grep")
    parser.add_argument("--current", action="store_true")
    parser.add_argument("--stale", action="store_true")
    parser.add_argument("--deprecated", action="store_true")
    parser.add_argument("--unverified", action="store_true")
    parser.add_argument("--now")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = args.bundle.resolve()
    if not root.is_dir():
        print(f"scanWithAdoc.py: {args.bundle} is not a directory", file=sys.stderr)
        return 2
    now = datetime.now(timezone.utc)
    if args.now:
        now = base.parse_timestamp(args.now)
        if now is None:
            print("scanWithAdoc.py: --now must be an RFC 3339 date-time with an offset", file=sys.stderr)
            return 2
    bundle = bundle_with_adoc_paths(base, root)
    concepts, collisions = [], {}
    not_concepts = []
    seen: dict[str, list[str]] = {}
    documents, core_collisions = discover(root)
    collisions.update(core_collisions)
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink() or not (path.name.endswith(".md") or path.name.endswith(".adoc")):
            continue
        relative = path.relative_to(root)
        if path.name in ("index.md", "log.md") or any(part.startswith(".") for part in relative.parts):
            continue
        resolved = path.resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        fmt = "asciidoc" if path.name.endswith(".adoc") else "markdown"
        metadata, problem = base.read_frontmatter(path)
        concept_type = metadata.get("type")
        if problem or not isinstance(concept_type, str) or not concept_type.strip():
            not_concepts.append({"path": relative.as_posix(), "format": fmt, "reason": problem or "no type"})
            continue
        identifier = relative.as_posix() if fmt == "asciidoc" else relative.with_suffix("").as_posix()
        seen.setdefault(identifier, []).append(relative.as_posix())
        concept = base.describe(bundle, path, metadata, now)
        concept["id"] = identifier
        concept["format"] = fmt
        concepts.append(concept)
    for identifier, paths in seen.items():
        if len(paths) > 1:
            collisions[identifier] = paths
    concepts = [c for c in concepts if c["id"] not in collisions]
    selection = argparse.Namespace(**vars(args))
    selected = [c for c in concepts if base.matches(c, selection, root)]
    metadata = bundle.metadata
    summary = {
        "concepts": len(concepts) + sum(len(paths) for paths in collisions.values()),
        "selected": len(selected),
        "not_concepts": len(not_concepts),
        "types": dict(Counter(str(c["type"]) for c in concepts).most_common()),
        "trust": {tier: sum(c["trust"] == tier for c in concepts) for tier in base.TRUST_ORDER},
        "stale": sum(c["stale"] for c in concepts),
        "deprecated": sum(c["status"] == "deprecated" for c in concepts),
        "draft": sum(c["status"] == "draft" for c in concepts),
        "not_current": sum(not c["current"] for c in concepts),
    }
    data = {
        "bundle": {
            "path": str(root),
            "title": metadata.get("title"),
            "description": metadata.get("description"),
            "license": metadata.get("license"),
        },
        "okf_version": bundle.okf_version,
        "now": now.isoformat(),
        "summary": summary,
        "concepts": selected,
        "not_concepts": not_concepts,
        "collisions": [{"id": identifier, "paths": paths} for identifier, paths in sorted(collisions.items())],
        "status": "collision" if collisions else "ok",
    }
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(f"Bundle {metadata.get('title') or root.name}: {summary['concepts']} concepts, status {data['status']}")
        for collision in data["collisions"]:
            print(f"collision {collision['id']}: {', '.join(collision['paths'])}")
        for concept in selected:
            print(f"{concept['id']}  [{concept['type']}]  {concept['trust']}, {concept['status']}")
    return 1 if collisions else 0


if __name__ == "__main__":
    sys.exit(main())
