import json
import shutil
import subprocess
from pathlib import Path

from tools.okf_adoc_core.profile import detect_profile

ROOT = Path(__file__).resolve().parents[1]


def run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(ROOT / script), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_profile_routing_requires_declaration_or_explicit_choice(tmp_path):
    profile, _ = detect_profile(tmp_path)
    assert profile == "okf-0.3"
    (tmp_path / "asset.adoc").write_text("AsciiDoc alone is not selection\n", encoding="utf-8")
    assert detect_profile(tmp_path)[0] == "okf-0.3"
    (tmp_path / "index.md").write_text(
        '---\nokf_version: "0.3"\nx-okf-profile: "okf-adoc/1.0"\n---\n',
        encoding="utf-8",
    )
    assert detect_profile(tmp_path)[0] == "okf-adoc/1.0"
    assert detect_profile(tmp_path, "okf-0.3")[0] == "okf-0.3"


def test_validator_checks_mixed_formats_links_includes_and_collisions(tmp_path):
    bundle = tmp_path / "bundle"
    (bundle / "metrics").mkdir(parents=True)
    (bundle / "index.md").write_text('---\nokf_version: "0.3"\n---\n', encoding="utf-8")
    (bundle / "metrics" / "a.adoc").write_text(
        "---\ntype: Metric\ntitle: A\n---\n"
        "= A\n:okf-type: Metric\n\n"
        "xref:/metrics/a.adoc#part[] <<missing.adoc#x>> include::b.adoc[]\n",
        encoding="utf-8",
    )
    (bundle / "metrics" / "a.adoc.md").write_text(
        "---\ntype: Metric\n---\n# A\n", encoding="utf-8"
    )
    (bundle / "metrics" / "b.adoc").write_text(
        "---\ntype: Metric\n---\n= B\n\nPartial\n", encoding="utf-8"
    )
    original = {p: p.read_bytes() for p in bundle.rglob("*") if p.is_file()}
    result = run(
        "skills/okf-generate-adoc/scripts/validateWithAdoc.py",
        str(bundle), "--json", "--now", "2026-01-01T00:00:00Z",
    )
    data = json.loads(result.stdout)
    codes = {finding["code"] for finding in data["findings"]}
    assert data["errors"] > 0
    assert "E130" in codes
    assert "A110" in codes
    assert "A113" in codes
    assert "A112" in codes
    assert all(path.read_bytes() == original[path] for path in original)


def test_scanner_reports_all_collision_paths_without_winner(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "a.adoc").write_text("---\ntype: Metric\n---\n= A\n\n", encoding="utf-8")
    (bundle / "a.adoc.md").write_text("---\ntype: Metric\n---\n# A\n", encoding="utf-8")
    result = run(
        "skills/okf-consume-adoc/scripts/scanWithAdoc.py",
        str(bundle), "--json", "--now", "2026-01-01T00:00:00Z",
    )
    data = json.loads(result.stdout)
    assert result.returncode == 1
    assert data["status"] == "collision"
    assert data["collisions"] == [{"id": "a.adoc", "paths": ["a.adoc", "a.adoc.md"]}]
    assert data["concepts"] == []


def test_cross_format_links_fragments_and_includes_resolve(tmp_path):
    bundle = tmp_path / "bundle"
    (bundle / "pages").mkdir(parents=True)
    (bundle / "tables").mkdir()
    (bundle / "index.md").write_text('---\nokf_version: "0.3"\n---\n', encoding="utf-8")
    (bundle / "pages" / "guide.md").write_text(
        "---\ntype: Reference\n---\n"
        "[AsciiDoc](../tables/schema.adoc) [Markdown](../tables/details.md)\n",
        encoding="utf-8",
    )
    (bundle / "tables" / "schema.adoc").write_text(
        "---\ntype: Table\n---\n= Schema\n\n"
        "link:details.md[details] xref:details.md#fields[] "
        "xref:#local[] <<#local>> <<schema.adoc#fields>> "
        "\\xref:missing.adoc[] include::partial.adoc[]\n",
        encoding="utf-8",
    )
    (bundle / "tables" / "details.md").write_text(
        "---\ntype: Reference\n---\n# Details\n", encoding="utf-8"
    )
    (bundle / "tables" / "partial.adoc").write_text("Included partial.\n", encoding="utf-8")
    result = run(
        "skills/okf-generate-adoc/scripts/validateWithAdoc.py",
        str(bundle), "--json", "--now", "2026-01-01T00:00:00Z",
    )
    data = json.loads(result.stdout)
    codes = {finding["code"] for finding in data["findings"]}
    assert not {"A111", "A112", "A113"} & codes


def test_asciidoc_computations_and_source_footnotes_are_discovered(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "index.md").write_text('---\nokf_version: "0.3"\n---\n', encoding="utf-8")
    (bundle / "calc.adoc").write_text(
        "---\ntype: Attested Computation\nruntime: python\n"
        "sources:\n  - id: source-1\n    resource: https://example.test/source\n"
        "---\n= Calculation\n\n"
        "== Computation\n[source,sql]\n----\nselect 1\n----\n"
        "Source note footnote:source-1[dataset] and footnote:missing[unknown]. "
        "footnoteref:[unknown-ref]\n",
        encoding="utf-8",
    )
    result = run(
        "skills/okf-generate-adoc/scripts/validateWithAdoc.py",
        str(bundle), "--json", "--now", "2026-01-01T00:00:00Z",
    )
    data = json.loads(result.stdout)
    findings = [finding for finding in data["findings"] if finding["path"] == "calc.adoc"]
    codes = {finding["code"] for finding in findings}
    assert "A120" in codes
    assert "A121" in codes
    assert "W112" not in codes
    assert "I205" in codes


def test_attribute_cli_is_read_only_until_write_and_write_is_idempotent(tmp_path):
    document = tmp_path / "x.adoc"
    original = (
        "---\r\ntype: Metric\r\ntitle: X\r\ntags: [\"a,b\", 'q\"x']\r\n---\r\n"
        "= X\r\n:toc:\r\n\r\nBody {okf-tags}\r\n"
    )
    document.write_bytes(original.encode())
    script = ROOT / "skills/okf-generate-adoc/scripts/syncAttributes.py"
    dry_run = subprocess.run(
        ["python3", str(script), str(document), "--dry-run"], capture_output=True, text=True
    )
    assert dry_run.returncode == 0
    assert document.read_bytes() == original.encode()
    diff = json.loads(dry_run.stdout)["files"][0]["diff"]
    assert 'okf-tags: "a,b","q""x"' in diff
    written = subprocess.run(
        ["python3", str(script), str(document), "--write"], capture_output=True, text=True
    )
    assert written.returncode == 0, written.stdout
    content = document.read_bytes()
    assert b":toc:\r\n" in content
    assert b":okf-concept-id: x.adoc\r\n" in content
    assert b":okf-tags: \"a,b\",\"q\"\"x\"\r\n" in content
    assert b"Body {okf-tags}\r\n" in content
    second = subprocess.run(
        ["python3", str(script), str(document), "--write"], capture_output=True, text=True
    )
    assert second.returncode == 0
    assert document.read_bytes() == content


def test_extended_skill_tools_run_without_other_skill_directories(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "m.adoc").write_text(
        "---\ntype: Metric\n---\n= Metric\n\nBody\n", encoding="utf-8"
    )
    copied = tmp_path / "consume-scripts"
    shutil.copytree(ROOT / "skills/okf-consume-adoc/scripts", copied)
    result = subprocess.run(
        ["python3", str(copied / "scanWithAdoc.py"), str(bundle), "--json"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["concepts"][0]["format"] == "asciidoc"
    validation = subprocess.run(
        ["python3", str(copied / "validateWithAdoc.py"), str(bundle), "--json"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert validation.returncode == 0
    generate_scripts = tmp_path / "generate-scripts"
    shutil.copytree(ROOT / "skills/okf-generate-adoc/scripts", generate_scripts)
    sync = subprocess.run(
        ["python3", str(generate_scripts / "syncAttributes.py"), str(bundle / "m.adoc"), "--dry-run"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert sync.returncode == 0
    assert json.loads(sync.stdout)["files"][0]["state"] == "missing"


def test_attribute_write_refuses_cross_format_id_collision(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    adoc = bundle / "a.adoc"
    adoc.write_text("---\ntype: Metric\n---\n= A\n\n", encoding="utf-8")
    markdown = bundle / "a.adoc.md"
    markdown.write_text("---\ntype: Metric\n---\n# A\n", encoding="utf-8")
    original = adoc.read_bytes()
    result = subprocess.run(
        [
            "python3",
            str(ROOT / "skills/okf-generate-adoc/scripts/syncAttributes.py"),
            str(bundle),
            "--write",
        ],
        capture_output=True,
        text=True,
    )
    data = json.loads(result.stdout)
    assert result.returncode == 2
    assert all(item["state"] == "conflict" for item in data["files"])
    assert adoc.read_bytes() == original
    assert markdown.read_text(encoding="utf-8").startswith("---")


def test_sync_refuses_symlink_inputs(tmp_path):
    target = tmp_path / "outside.adoc"
    target.write_text("---\ntype: Metric\n---\n= A\n\n", encoding="utf-8")
    link = tmp_path / "link.adoc"
    link.symlink_to(target)
    result = subprocess.run(
        [
            "python3",
            str(ROOT / "skills/okf-generate-adoc/scripts/syncAttributes.py"),
            str(link),
            "--write",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert target.read_text(encoding="utf-8").endswith("= A\n\n")
