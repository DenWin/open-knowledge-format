import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLES = ("acme_retail", "crypto_bitcoin", "ga4", "stackoverflow")
NOW = "2026-01-01T00:00:00Z"

GOLDEN = {
    ("validate", "acme_retail"): "2f94bb4bfefd1c04e866449b823df438d3ee747232457a7f11cac15bd0c7f059",
    ("scan", "acme_retail"): "126da2c5ad1f176b916ad791f05006ba21123ed9edc4741b90670994ee07c898",
    ("validate", "crypto_bitcoin"): "44b06784b3051e8243096bedb5c08e5199b48f35e920ed742d3c647f7fcf9fcf",
    ("scan", "crypto_bitcoin"): "b7227cb79e0d2272833e8cd9bc331e3f9b2fc6f8a5df4f55f0f80cd3b69abbfa",
    ("validate", "ga4"): "234524b087d062e4e316b555b8f97be587a2f7b05b70235ae154481091d56382",
    ("scan", "ga4"): "481757ff813f80b0bcf6fb9a28e17b96b1701cd91164ac049eecb56ebea170ee",
    ("validate", "stackoverflow"): "0c20fbbce124e6b2125aa892411dbeb31530a04cf80e302d4e8c3e9c989eb0ae",
    ("scan", "stackoverflow"): "bbe7ca78d9fb5ab52301ed8eaa0103e762bcc39e005bfd60cf36d0b6b8053c7b",
}


def cli(kind: str, bundle: str, extended: bool = False) -> subprocess.CompletedProcess[str]:
    if kind == "validate":
        script = (
            "skills/okf-generate-adoc/scripts/validateWithAdoc.py"
            if extended else "skills/okf-generate/scripts/validate.py"
        )
    else:
        script = (
            "skills/okf-consume-adoc/scripts/scanWithAdoc.py"
            if extended else "skills/okf-consume/scripts/scan.py"
        )
    return subprocess.run(
        ["python3", str(ROOT / script), str(ROOT / "bundles" / bundle), "--json", "--now", NOW],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )


def normalized_digest(output: str, bundle: str) -> str:
    output = output.replace(str(ROOT / "bundles" / bundle), "<BUNDLE>")
    return hashlib.sha256(output.encode()).hexdigest()


def test_immutable_upstream_checksums():
    result = subprocess.run(
        ["sha256sum", "--check", "tests/baseline/immutable.sha256"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_original_json_goldens():
    for kind in ("validate", "scan"):
        for bundle in BUNDLES:
            result = cli(kind, bundle)
            assert result.returncode == 0, result.stderr
            assert normalized_digest(result.stdout, bundle) == GOLDEN[(kind, bundle)]


def test_extended_validator_matches_markdown_only_baseline():
    for bundle in BUNDLES:
        original, extended = cli("validate", bundle), cli("validate", bundle, extended=True)
        assert original.returncode == extended.returncode == 0
        assert json.loads(extended.stdout) == json.loads(original.stdout)


def test_extended_scanner_preserves_markdown_findings_and_fields():
    for bundle in BUNDLES:
        original, extended = cli("scan", bundle), cli("scan", bundle, extended=True)
        assert original.returncode == extended.returncode == 0
        before, after = json.loads(original.stdout), json.loads(extended.stdout)
        assert after["summary"] == before["summary"]
        assert after["bundle"] == before["bundle"]
        assert after["okf_version"] == before["okf_version"]
        assert after["now"] == before["now"]
        assert after["not_concepts"] == [
            {**item, "format": "markdown"} for item in before["not_concepts"]
        ]
        stripped = [{key: value for key, value in item.items() if key != "format"} for item in after["concepts"]]
        assert stripped == before["concepts"]
        assert after["collisions"] == []
        assert after["status"] == "ok"
