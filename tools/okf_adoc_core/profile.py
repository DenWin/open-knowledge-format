#!/usr/bin/env python3
"""Canonical profile routing, identity, header, and metadata synchronization.

This module intentionally implements an opt-in profile layered on OKF v0.3;
it does not alter or redefine the official Markdown format.
"""

from __future__ import annotations

import csv
import io
import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

PROFILE = "okf-adoc/1.0"
DEFAULT_ATTRIBUTES = {
    "type": "okf-type",
    "title": "okf-title",
    "description": "okf-description",
    "status": "okf-status",
    "tags": "okf-tags",
}
MANAGED_ATTRIBUTES = {"okf-concept-id", *DEFAULT_ATTRIBUTES.values()}
ATTRIBUTE_RE = re.compile(r"^:([A-Za-z0-9_.-]+):(?:[ \t]*(.*))?$")
TITLE_RE = re.compile(r"^= .+\s*$")
REVISION_RE = re.compile(r"^(?:v?\d+(?:\.\d+)*,|20\d{2}-\d{2}-\d{2}\b).*$")
SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
MACRO_RE = re.compile(r"(?<!\\)\b(?:link|xref):([^\s\[]+)\[")
SHORTHAND_RE = re.compile(r"(?<!\\)<<([^>,#]*)(?:#([^>,]+))?(?:,[^>]*)?>>")
INCLUDE_RE = re.compile(r"(?<!\\)\binclude::([^\s\[]+)\[")


@dataclass(frozen=True)
class Finding:
    code: str
    message: str
    level: str = "warning"
    line: int | None = None


@dataclass
class Concept:
    path: Path
    concept_id: str
    format: str
    metadata: dict[str, Any]
    body: str
    frontmatter_error: str | None = None


@dataclass
class Header:
    start: int
    end: int
    separator: int | None
    title: bool
    author_or_revision: bool
    entries: list[tuple[int, str, str]]
    findings: list[Finding] = field(default_factory=list)


@dataclass
class AttributePlan:
    expected: dict[str, str]
    state: str
    findings: list[Finding]
    updated_text: str | None = None


class StyledString(str):
    def __new__(cls, value: str, yaml_style: str | None) -> "StyledString":
        instance = super().__new__(cls, value)
        instance.yaml_style = yaml_style
        return instance


def _safe_yaml(text: str) -> Any:
    class Loader(yaml.SafeLoader):
        def construct_yaml_str(self, node: yaml.ScalarNode) -> StyledString:
            return StyledString(super().construct_yaml_str(node), node.style)

        def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
            seen = set()
            for key_node, _ in node.value:
                key = self.construct_object(key_node, deep=deep)
                try:
                    duplicate = key in seen
                    seen.add(key)
                except TypeError as exc:
                    raise yaml.constructor.ConstructorError(
                        "while constructing a mapping", node.start_mark,
                        "found an unhashable mapping key", key_node.start_mark,
                    ) from exc
                if duplicate:
                    raise yaml.constructor.ConstructorError(
                        "while constructing a mapping", node.start_mark,
                        f"found duplicate key {key!r}", key_node.start_mark,
                    )
            return super().construct_mapping(node, deep=deep)

    Loader.add_constructor("tag:yaml.org,2002:str", Loader.construct_yaml_str)
    Loader.yaml_implicit_resolvers = {
        key: [
            resolver
            for resolver in resolvers
            if resolver[0] != "tag:yaml.org,2002:timestamp"
        ]
        for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
    }
    return yaml.load(text, Loader=Loader)


def split_frontmatter(text: str) -> tuple[dict[str, Any], str, str | None, int]:
    """Return metadata, body, parse error, and the 1-based body start line."""
    bom = "\ufeff" if text.startswith("\ufeff") else ""
    lines = text[len(bom):].splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        return {}, text, "frontmatter is absent", 1
    for index in range(1, len(lines)):
        if lines[index].rstrip("\r\n") == "---":
            raw = "".join(lines[1:index])
            body = "".join(lines[index + 1:])
            try:
                metadata = _safe_yaml(raw)
            except yaml.YAMLError as exc:
                return {}, body, f"invalid YAML: {exc}", index + 2
            if metadata is None:
                metadata = {}
            if not isinstance(metadata, dict):
                return {}, body, "frontmatter is not a mapping", index + 2
            return metadata, body, None, index + 2
    return {}, "", "frontmatter is not closed", len(lines) + 1


def relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def concept_id(path: Path, root: Path) -> str:
    """Derive identity: Markdown loses its final suffix; AsciiDoc retains it."""
    relative = relative_path(path, root)
    if relative.endswith(".md"):
        return relative[:-3]
    if relative.endswith(".adoc"):
        return relative
    raise ValueError(f"not an OKF concept extension: {relative}")


def discover(root: Path) -> tuple[list[Concept], dict[str, list[str]]]:
    """Read candidate documents without following symlinks outside root."""
    root = root.resolve()
    documents: list[Concept] = []
    by_id: dict[str, list[str]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part.startswith(".") for part in relative.parts):
            continue
        if relative.name in {"index.md", "log.md"}:
            continue
        if not (path.name.endswith(".md") or path.name.endswith(".adoc")):
            continue
        if path.is_symlink() or not path.is_file():
            continue
        resolved = path.resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        if path.name.endswith(".md"):
            metadata, body, error, _ = split_frontmatter(path.read_text(encoding="utf-8"))
            fmt = "markdown"
        else:
            metadata, body, error, _ = split_frontmatter(path.read_text(encoding="utf-8"))
            fmt = "asciidoc"
        # A non-OKF AsciiDoc file is still included for format validation; only
        # frontmatter-bearing or typed files are candidate concepts.
        if error == "frontmatter is absent" and fmt == "markdown":
            continue
        if not metadata and fmt == "asciidoc" and error == "frontmatter is absent":
            continue
        cid = concept_id(path, root)
        item = Concept(path, cid, fmt, metadata, body, None if error == "frontmatter is absent" else error)
        documents.append(item)
        by_id.setdefault(cid, []).append(relative.as_posix())
    return documents, {key: values for key, values in by_id.items() if len(values) > 1}


def detect_profile(root: Path, explicit: str | None = None) -> tuple[str, list[Finding]]:
    """Explicit selection wins; otherwise recognize only index metadata."""
    if explicit:
        if explicit not in {"okf-0.3", PROFILE}:
            return explicit, [Finding("unknown-profile", f"Unknown explicit profile {explicit!r}", "error")]
        return explicit, []
    index = root / "index.md"
    if index.is_file():
        metadata, _, error, _ = split_frontmatter(index.read_text(encoding="utf-8"))
        declared = metadata.get("x-okf-profile") if not error else None
        if declared == PROFILE and metadata.get("okf_version") == "0.3":
            return PROFILE, []
        if declared not in (None, ""):
            return "okf-0.3", [
                Finding("unknown-profile", f"Unrecognized x-okf-profile {declared!r}; using standard OKF v0.3", "warning")
            ]
    return "okf-0.3", []


def _attribute_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    if "\n" in value or "\r" in value or "\0" in value:
        return None
    # Attribute references and substitutions are deliberately not escaped or
    # expanded: reject them rather than allowing document data to inject them.
    if "{" in value or "}" in value or value.startswith(":"):
        return None
    return value


def _tag_value(value: Any) -> str | None:
    if value is None or value == "":
        return None
    values = value if isinstance(value, list) else [value]
    if any(not isinstance(item, str) or "\n" in item or "\r" in item or "\0" in item for item in values):
        return None
    if any("{" in item or "}" in item for item in values):
        return None
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(values)
    return output.getvalue()


def attribute_plan(
    metadata: dict[str, Any],
    identifier: str,
    *,
    mappings: dict[str, str] | None = None,
    value_mappings: dict[str, dict[str, str]] | None = None,
) -> tuple[dict[str, str], list[Finding]]:
    """Map canonical YAML values to safe native attributes, one way only."""
    expected: dict[str, str] = {}
    findings: list[Finding] = []
    safe_identifier = _attribute_string(identifier)
    if safe_identifier is None:
        findings.append(Finding("unsupported-value", "derived Concept ID cannot be represented safely as okf-concept-id"))
    else:
        expected["okf-concept-id"] = safe_identifier
    mapping = dict(DEFAULT_ATTRIBUTES)
    if mappings:
        mapping.update(mappings)
    if len(set(mapping.values())) != len(mapping):
        findings.append(Finding("invalid-mapping", "each YAML source must map to a distinct AsciiDoc attribute", "error"))
    for source, target in mapping.items():
        if not re.fullmatch(r"okf-[a-z0-9][a-z0-9-]*", target):
            findings.append(Finding("invalid-mapping", f"Invalid managed attribute name {target!r}", "error"))
            continue
        if source not in metadata or metadata[source] is None or metadata[source] == "" or metadata[source] == []:
            continue
        value = metadata[source]
        if source == "tags":
            converted = _tag_value(value)
        elif source == "description":
            # Remove only the final newline introduced by block-scalar
            # chomping; explicit newlines in quoted/plain values are data.
            if (
                isinstance(value, str)
                and value.endswith("\n")
                and getattr(value, "yaml_style", None) in ("|", ">")
            ):
                value = value[:-1]
            converted = _attribute_string(value)
        else:
            converted = _attribute_string(value)
        if source == "status":
            allowed = {"draft", "stable", "deprecated"}
            if isinstance(value, str) and value not in allowed:
                replacement = (value_mappings or {}).get(source, {}).get(value)
                if replacement in allowed:
                    converted = replacement
                    findings.append(Finding(
                        "explicit-value-mapping",
                        f"status {value!r} explicitly maps to {replacement!r}",
                        "info",
                    ))
                else:
                    converted = None
            elif not isinstance(value, str):
                converted = None
        if converted is None:
            findings.append(Finding("unsupported-value", f"{source!r} cannot be represented safely as {target}", "warning"))
            continue
        expected[target] = converted
    return expected, findings


def parse_header(body: str) -> Header:
    """Parse top-of-body AsciiDoc header through the first blank line."""
    lines = body.splitlines()
    if not lines:
        return Header(0, 0, None, False, False, [], [
            Finding("missing-header", "AsciiDoc body has no document header", "error", 1)
        ])
    sep = next((idx for idx, line in enumerate(lines) if not line.strip()), None)
    top = lines if sep is None else lines[:sep]
    findings: list[Finding] = []
    title_index = next((i for i, line in enumerate(lines) if TITLE_RE.match(line)), None)
    first_nonblank = next((i for i, line in enumerate(lines) if line.strip()), None)
    title = bool(first_nonblank == 0 and top and TITLE_RE.match(top[0]))
    if title_index is not None and title_index != 0:
        findings.append(Finding("late-title", "Level-0 title is not at the top; attributes below it are body content", "error", title_index + 1))
    if first_nonblank not in (None, 0) and title_index is None:
        findings.append(Finding("missing-header", "Document header must begin at the top of the AsciiDoc body", "error", first_nonblank + 1))
    entries: list[tuple[int, str, str]] = []
    start = 1 if title else 0
    author_or_revision = False
    for index in range(start, len(top)):
        line = top[index]
        match = ATTRIBUTE_RE.match(line)
        if match:
            entries.append((index, match.group(1), match.group(2) or ""))
            continue
        if title and index == 1 and line.strip() and not line.startswith(":"):
            # Asciidoctor accepts this as an author line, even when unintended.
            author_or_revision = True
            findings.append(Finding("possible-author-line", "Plain text directly below the title is parsed as an author line", "warning", index + 1))
            continue
        if title and index == 2 and line.strip() and REVISION_RE.match(line):
            author_or_revision = True
            continue
        if line.casefold().startswith(":okf-"):
            findings.append(Finding("invalid-attribute", f"Invalid AsciiDoc attribute entry {line!r}", "error", index + 1))
        elif entries or title:
            findings.append(Finding("invalid-header-line", f"Unexpected content in document header: {line!r}", "error", index + 1))
        else:
            findings.append(Finding("missing-header", "Body text appears before a document header", "error", index + 1))
            break
    return Header(0, len(top), sep, title, author_or_revision, entries, findings)


def sync_attributes(
    text: str,
    metadata: dict[str, Any],
    identifier: str,
    *,
    write: bool = False,
    mappings: dict[str, str] | None = None,
    value_mappings: dict[str, dict[str, str]] | None = None,
) -> AttributePlan:
    """Inspect or reconcile generated attributes without touching YAML/body."""
    bom = "\ufeff" if text.startswith("\ufeff") else ""
    metadata_block, body, fm_error, body_line = split_frontmatter(text)
    if fm_error not in (None, "frontmatter is absent"):
        return AttributePlan({}, "unsupported", [Finding("frontmatter-error", fm_error, "error")])
    header = parse_header(body)
    expected, findings = attribute_plan(
        metadata, identifier, mappings=mappings, value_mappings=value_mappings
    )
    findings = header.findings + findings
    if header.findings:
        return AttributePlan(expected, "unsupported", findings)
    if any(f.code == "unsupported-value" for f in findings):
        return AttributePlan(expected, "unsupported", findings)
    if header.separator is None:
        findings.append(Finding("missing-separator", "Document header must be followed by an empty line", "error"))
        return AttributePlan(expected, "unsupported", findings)
    actual: dict[str, list[tuple[int, str, str]]] = {}
    for index, name, value in header.entries:
        if name.casefold().startswith("okf-"):
            actual.setdefault(name.casefold(), []).append((index, value, name))
    errors = any(f.level == "error" for f in findings)
    if errors:
        return AttributePlan(expected, "unsupported", findings)

    conflicts = []
    for name, entries in actual.items():
        if len(entries) > 1:
            conflicts.append(Finding("duplicate-attribute", f"{name} appears more than once", "error", entries[1][0] + body_line))
        elif name not in expected:
            conflicts.append(Finding("obsolete-attribute", f"{name} has no canonical YAML source", "warning", entries[0][0] + body_line))
        elif entries[0][1] != expected[name] or entries[0][2] != name:
            conflicts.append(Finding("outdated-attribute", f"{name} differs from its canonical YAML value", "warning", entries[0][0] + body_line))
    missing = [name for name in expected if name not in actual]
    for name in missing:
        conflicts.append(Finding("missing-attribute", f"{name} is missing", "warning"))
    if any(f.level == "error" for f in conflicts):
        state = "conflict"
    elif any(f.code == "outdated-attribute" for f in conflicts):
        state = "outdated"
    elif any(f.code in {"obsolete-attribute", "missing-attribute"} for f in conflicts):
        state = "missing" if missing else "outdated"
    else:
        state = "ok"
    findings.extend(conflicts)
    if not write or state == "unsupported":
        return AttributePlan(expected, state, findings)

    # Only the already-established header may be changed. Never normalize a
    # late title or insert under a section/body line.
    lines = body.splitlines(keepends=True)
    sep_line_index = header.separator
    newline = "\r\n" if "\r\n" in body else "\n"
    managed_line_idxs = {entry[0] for entry in header.entries if entry[1].casefold().startswith("okf-")}
    replacement: list[str] = []
    for idx, line in enumerate(lines[:sep_line_index]):
        if idx in managed_line_idxs:
            continue
        replacement.append(line)
    if replacement and not replacement[-1].endswith(("\n", "\r")):
        replacement[-1] += newline
    for name, value in expected.items():
        replacement.append(f":{name}: {value}{newline}")
    new_body = "".join(replacement) + "".join(lines[sep_line_index:])
    new_text = bom + new_body if bom else new_body
    # Frontmatter, including original line endings and spelling, must remain
    # byte-identical. Recover its exact prefix rather than serializing YAML.
    if text.startswith(bom + "---"):
        fm_lines = text[len(bom):].splitlines(keepends=True)
        closing = next((i for i, line in enumerate(fm_lines[1:], 1) if line.rstrip("\r\n") == "---"), None)
        if closing is not None:
            prefix = bom + "".join(fm_lines[:closing + 1])
            if prefix.endswith(("\n", "\r")):
                new_text = prefix + new_body
            else:
                new_text = prefix + newline + new_body
    return AttributePlan(expected, state, findings, new_text)


def resolve_target(root: Path, source: Path, target: str) -> Path | None:
    """Resolve an in-bundle target while rejecting traversal and symlink escape."""
    if SCHEME_RE.match(target) or target.startswith("//"):
        return None
    clean = urllib.parse.unquote(target.split("#", 1)[0].split("?", 1)[0])
    base = root if clean.startswith("/") else source.parent
    candidate = (base / clean.lstrip("/")).resolve()
    root = root.resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def targets(body: str) -> Iterable[tuple[str, str, int]]:
    """Yield (kind, target, 1-based line) for AsciiDoc references."""
    for line_no, line in enumerate(body.splitlines(), start=1):
        for match in MACRO_RE.finditer(line):
            yield match.group(0).split(":", 1)[0], match.group(1), line_no
        for match in SHORTHAND_RE.finditer(line):
            yield "shorthand", match.group(1) + (f"#{match.group(2)}" if match.group(2) else ""), line_no
        for match in INCLUDE_RE.finditer(line):
            yield "include", match.group(1), line_no
