import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_copilot_marketplace_points_to_agent_plugin_bundle():
    catalog = json.loads((ROOT / ".github/plugin/marketplace.json").read_text(encoding="utf-8"))
    assert catalog["name"] == "open-knowledge-format"
    assert len(catalog["plugins"]) == 1
    entry = catalog["plugins"][0]
    assert entry["name"] == "okf"
    assert entry["source"] == "plugins/okf"
    plugin = ROOT / entry["source"]
    manifest = json.loads((plugin / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    assert manifest["name"] == entry["name"]
    assert manifest["version"] == entry["version"]
    assert manifest["description"] == entry["description"]


def test_copilot_plugin_bundles_all_skills_and_adoption_agent():
    plugin_skills = ROOT / "plugins/okf/skills"
    expected = {
        "okf-generate",
        "okf-consume",
        "okf-generate-adoc",
        "okf-consume-adoc",
    }
    assert {
        path.name for path in plugin_skills.iterdir()
        if (path / "SKILL.md").is_file()
    } == expected
    agent = ROOT / "plugins/okf/com.github.copilot/agents/okf-adoption.agent.md"
    repository_agent = ROOT / ".github/agents/okf-adoption.agent.md"
    assert agent.read_bytes() == repository_agent.read_bytes()


def test_generated_copilot_bundle_is_current():
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/okf_adoc_core/check_generated.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_adoption_agent_prefers_declared_available_skill_pair():
    canonical = (
        ROOT / "tools/okf_adoc_core/okf-adoption.agent.md"
    ).read_text(encoding="utf-8")
    assert "If only\n  one pair is available, use that pair." in canonical
    assert "Prefer the extended pair" in canonical
