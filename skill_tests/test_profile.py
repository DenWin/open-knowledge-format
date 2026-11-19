from pathlib import Path

from tools.okf_adoc_core.profile import (
    attribute_plan,
    concept_id,
    discover,
    parse_header,
    resolve_target,
    split_frontmatter,
    sync_attributes,
    targets,
)


def test_concept_identity_is_format_specific(tmp_path: Path):
    root = tmp_path
    assert concept_id(root / "a.md", root) == "a"
    assert concept_id(root / "a.adoc", root) == "a.adoc"
    assert concept_id(root / "a.adoc.md", root) == "a.adoc"


def test_discovery_reports_collisions_and_ignores_asset_extensions(tmp_path: Path):
    (tmp_path / "a.adoc").write_text("---\ntype: Metric\n---\n", encoding="utf-8")
    (tmp_path / "a.adoc.md").write_text("---\ntype: Metric\n---\n", encoding="utf-8")
    (tmp_path / "x.asciidoc").write_text("---\ntype: Metric\n---\n", encoding="utf-8")
    (tmp_path / "X.ADOC").write_text("---\ntype: Metric\n---\n", encoding="utf-8")
    documents, collisions = discover(tmp_path)
    assert collisions == {"a.adoc": ["a.adoc", "a.adoc.md"]}
    assert {doc.path.name for doc in documents} == {"a.adoc", "a.adoc.md"}


def test_tag_encoding_and_description_conversion():
    expected, findings = attribute_plan(
        {"tags": ["alpha", "with,comma", 'with"quote']}, "metrics/a"
    )
    assert expected["okf-tags"] == 'alpha,"with,comma","with""quote"'
    assert not findings
    metadata, _, error, _ = split_frontmatter(
        "---\ndescription: |\n  one sentence\n---\n"
    )
    assert error is None
    expected, findings = attribute_plan(metadata, "metrics/a")
    assert expected["okf-description"] == "one sentence"
    assert not findings
    expected, findings = attribute_plan({"tags": "one,two", "description": "first\nsecond"}, "a")
    assert expected["okf-tags"] == '"one,two"'
    assert "okf-description" not in expected
    assert findings[0].code == "unsupported-value"


def test_absent_optional_metadata_is_not_materialized():
    expected, findings = attribute_plan({}, "metric/a")
    assert expected == {"okf-concept-id": "metric/a"}
    assert not findings
    expected, findings = attribute_plan(
        {"type": None, "title": None, "description": None, "status": None, "tags": None},
        "metric/a",
    )
    assert expected == {"okf-concept-id": "metric/a"}
    assert not findings


def test_legacy_status_requires_explicit_value_mapping():
    expected, findings = attribute_plan({"status": "accepted"}, "metric/a")
    assert "okf-status" not in expected
    assert any(item.code == "unsupported-value" for item in findings)
    expected, findings = attribute_plan(
        {"status": "accepted"},
        "metric/a",
        value_mappings={"status": {"accepted": "stable"}},
    )
    assert expected["okf-status"] == "stable"
    assert any(item.code == "explicit-value-mapping" for item in findings)


def test_extension_attributes_require_explicit_reproducible_mapping():
    expected, findings = attribute_plan({"x-label": "Owner"}, "metric/a")
    assert "okf-x-label" not in expected
    expected, findings = attribute_plan(
        {"x-label": "Owner"},
        "metric/a",
        mappings={"x-label": "okf-x-label"},
    )
    assert expected["okf-x-label"] == "Owner"
    assert not findings


def test_header_allows_titleless_and_rejects_late_title():
    header = parse_header(":toc:\n:okf-type: Metric\n\nBody\n")
    assert not header.findings
    late = parse_header("Body first\n\n= Late title\n:okf-type: Metric\n\n")
    assert any(item.code == "late-title" for item in late.findings)
    assert any(item.code == "missing-header" for item in late.findings)


def test_revision_and_unrelated_header_attributes_are_preserved():
    header = parse_header(
        "= Title\nAuthor Name\nv1.2, 2025-01-01: Draft\n:custom.attr: keep\n\nBody\n"
    )
    assert any(item.code == "possible-author-line" for item in header.findings)
    assert not any(item.level == "error" for item in header.findings)
    assert [(name, value) for _, name, value in header.entries] == [("custom.attr", "keep")]


def test_cross_reference_grammar_handles_local_fragments_and_paths():
    found = list(targets("xref:#intro[] <<#details>> <<metrics/a.adoc#part, Metric>>\n"))
    assert found == [
        ("xref", "#intro", 1),
        ("shorthand", "#details", 1),
        ("shorthand", "metrics/a.adoc#part", 1),
    ]


def test_sync_is_idempotent_and_preserves_yaml_and_body():
    text = (
        "---\ntype: Metric\ntitle: Revenue\nstatus: stable\ntags: [finance]\n"
        "---\n= Revenue\n:toc:\n\nText {okf-status}.\n"
    )
    metadata, _, error, _ = split_frontmatter(text)
    assert error is None
    planned = sync_attributes(text, metadata, "metrics/revenue")
    assert planned.state == "missing"
    assert planned.updated_text is None
    written = sync_attributes(text, metadata, "metrics/revenue", write=True)
    assert written.updated_text is not None
    assert "---\ntype: Metric\ntitle: Revenue\nstatus: stable\ntags: [finance]\n---\n" in written.updated_text
    assert ":toc:\n:okf-concept-id: metrics/revenue\n" in written.updated_text
    assert written.updated_text.endswith("Text {okf-status}.\n")
    again = sync_attributes(written.updated_text, metadata, "metrics/revenue", write=True)
    assert again.state == "ok"
    assert again.updated_text == written.updated_text


def test_write_never_inserts_under_late_title():
    text = "---\ntype: Metric\n---\nBody first\n\n= Late title\n\n"
    metadata, _, _, _ = split_frontmatter(text)
    plan = sync_attributes(text, metadata, "a", write=True)
    assert plan.state == "unsupported"
    assert plan.updated_text is None
    assert text == "---\ntype: Metric\n---\nBody first\n\n= Late title\n\n"


def test_paths_do_not_escape_root(tmp_path: Path):
    root = tmp_path / "bundle"
    root.mkdir()
    source = root / "metrics" / "m.adoc"
    source.parent.mkdir()
    outside = tmp_path / "outside.adoc"
    outside.write_text("outside", encoding="utf-8")
    assert resolve_target(root, source, "/metrics/x.adoc") == root / "metrics" / "x.adoc"
    assert resolve_target(root, source, "../../outside.adoc") is None
    (root / "escape").symlink_to(tmp_path, target_is_directory=True)
    assert resolve_target(root, source, "../escape/outside.adoc") is None


def test_unsafe_yaml_and_duplicate_keys_are_rejected():
    _, _, error, _ = split_frontmatter(
        "---\ntype: !!python/object/apply:os.system ['echo unsafe']\n---\n"
    )
    assert error and error.startswith("invalid YAML:")
    _, _, error, _ = split_frontmatter("---\ntype: Metric\ntype: Policy\n---\n")
    assert error and "duplicate key" in error


def test_unsafe_attribute_values_and_manual_namespace_entries_are_reported():
    text = "---\ntype: Metric\ntitle: '{secret}'\n---\n:okf-manual: value\n\nBody\n"
    metadata, _, error, _ = split_frontmatter(text)
    assert error is None
    plan = sync_attributes(text, metadata, "a.adoc")
    assert plan.state == "unsupported"
    assert any(item.code == "unsupported-value" for item in plan.findings)
    assert plan.updated_text is None


def test_duplicate_and_obsolete_attributes_are_visible_and_reconciled():
    text = (
        "---\ntype: Metric\n---\n= A\n:okf-type: Old\n:okf-type: Duplicate\n"
        ":okf-legacy: manual\n:custom: retain\n\nBody\n"
    )
    metadata, _, _, _ = split_frontmatter(text)
    checked = sync_attributes(text, metadata, "a.adoc")
    assert checked.state == "conflict"
    codes = {item.code for item in checked.findings}
    assert {"duplicate-attribute", "obsolete-attribute"} <= codes
    updated = sync_attributes(text, metadata, "a.adoc", write=True)
    assert updated.updated_text is not None
    assert ":okf-type: Metric\n" in updated.updated_text
    assert updated.updated_text.count(":okf-type:") == 1
    assert ":okf-legacy:" not in updated.updated_text
    assert ":custom: retain\n" in updated.updated_text
