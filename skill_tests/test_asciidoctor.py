import shutil
import subprocess

import pytest

from tools.okf_adoc_core.profile import split_frontmatter, sync_attributes


@pytest.mark.parametrize(
    ("source", "identifier"),
    [
        (
            "---\ntype: Metric\nstatus: stable\ntags: [\"a,b\", 'q\"x']\n---\n"
            "= Revenue\n\nStatus: {okf-status}\nTags: {okf-tags}\n",
            "revenue.adoc",
        ),
        (
            "---\ntype: Metric\nstatus: stable\ntags: [\"a,b\", 'q\"x']\n---\n"
            ":toc:\n\nStatus: {okf-status}\nTags: {okf-tags}\ninclude::partial.adoc[]\n",
            "revenue.adoc",
        ),
    ],
)
def test_skip_front_matter_and_attribute_substitution(source, identifier, tmp_path):
    executable = shutil.which("asciidoctor")
    if not executable:
        pytest.skip("Asciidoctor is installed by the skill-suite CI workflow")
    document = tmp_path / "concept.adoc"
    document.write_text(source, encoding="utf-8")
    metadata, _, error, _ = split_frontmatter(source)
    assert error is None
    plan = sync_attributes(source, metadata, identifier, write=True)
    assert plan.updated_text is not None
    document.write_text(plan.updated_text, encoding="utf-8")
    (tmp_path / "partial.adoc").write_text("Included {okf-status}.\n", encoding="utf-8")
    result = subprocess.run(
        [executable, "-a", "skip-front-matter", "-o", "-", str(document)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Status: stable" in result.stdout
    assert 'Tags: "a,b","q""x"' in result.stdout
    if "include::partial.adoc[]" in source:
        assert "Included stable." in result.stdout
    assert "type: Metric" not in result.stdout
