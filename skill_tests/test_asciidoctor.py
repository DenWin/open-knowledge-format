import shutil
import subprocess

import pytest


@pytest.mark.parametrize(
    "source",
    [
        "---\ntype: Metric\n---\n= Revenue\n:okf-status: stable\n\nStatus: {okf-status}\n",
        "---\ntype: Metric\n---\n:okf-status: stable\n\nStatus: {okf-status}\n",
    ],
)
def test_skip_front_matter_and_attribute_substitution(source, tmp_path):
    executable = shutil.which("asciidoctor")
    if not executable:
        pytest.skip("Asciidoctor is installed by the skill-suite CI workflow")
    document = tmp_path / "concept.adoc"
    document.write_text(source, encoding="utf-8")
    result = subprocess.run(
        [executable, "-a", "skip-front-matter", "-o", "-", str(document)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Status: stable" in result.stdout
    assert "type: Metric" not in result.stdout
