from pathlib import Path

from tools.okf_adoc_core.profile import (
    attribute_plan,
    concept_id,
    discover,
    parse_header,
    resolve_target,
    split_frontmatter,
    sync_attributes,
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
        {"tags": ["alpha", "with,comma", 'with"quote'], "description": "one sentence\n"},
        "metrics/a",
    )
    assert expected["okf-tags"] == 'alpha,"with,comma","with""quote"'
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


def test_header_allows_titleless_and_rejects_late_title():
    header = parse_header(":toc:\n:okf-type: Metric\n\nBody\n")
    assert not header.findings
    late = parse_header("Body first\n\n= Late title\n:okf-type: Metric\n\n")
    assert any(item.code == "late-title" for item in late.findings)
    assert any(item.code == "missing-header" for item in late.findings)


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
