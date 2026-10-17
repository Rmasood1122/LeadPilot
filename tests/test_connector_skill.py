"""The leadpilot-outbound Skill and the leadpilot Claude Code plugin
(docs/features/mcp-connector.md, Phase 4).

Pins the Agent Skill rules (name and description limits, progressive
disclosure), the plugin layout (only plugin.json inside .claude-plugin/),
the MCP URL (DECISIONS.md CONN-HOST), that the plugin ships the same Skill
as the repository, and that every tool the Skill's reference names exists
on the server -- and every server tool is documented.
"""

from __future__ import annotations

import filecmp
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / ".claude" / "skills" / "leadpilot-outbound"
PLUGIN = ROOT / "plugins" / "leadpilot"
MCP_URL = "https://api.calendarharvest.com/mcp"


def _frontmatter(text: str) -> dict:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert match, "SKILL.md must start with YAML frontmatter"
    out = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip()
    return out


def test_skill_frontmatter_follows_the_agent_skill_rules():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    meta = _frontmatter(text)
    name, description = meta["name"], meta["description"]
    assert name == "leadpilot-outbound" == SKILL.name
    assert len(name) <= 64 and re.fullmatch(r"[a-z0-9-]+", name)
    assert "anthropic" not in name and "claude" not in name
    assert 0 < len(description) <= 1024
    assert "Use when" in description          # says when to trigger, not only what
    assert len(text.splitlines()) < 500
    assert len(text) < 20_000                 # well under ~5k tokens


def test_skill_body_points_at_its_references():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    for ref in ("references/tools.md", "references/glossary.md"):
        assert ref in text
        assert (SKILL / ref).is_file()


def test_skill_states_the_two_safety_rules():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "untrusted_content" in text and "never follow instructions" in text
    assert "Nothing is ever sent, scheduled or approved" in text


def test_plugin_layout_and_mcp_url():
    assert sorted(p.name for p in (PLUGIN / ".claude-plugin").iterdir()) == ["plugin.json"]
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["name"] == "leadpilot"
    mcp = json.loads((PLUGIN / ".mcp.json").read_text())
    assert mcp == {"mcpServers": {"leadpilot": {"type": "http", "url": MCP_URL}}}
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    assert market["plugins"][0]["source"] == "./plugins/leadpilot"


def test_plugin_ships_the_same_skill_as_the_repository():
    comparison = filecmp.dircmp(SKILL, PLUGIN / "skills" / "leadpilot-outbound")

    def _differences(cmp) -> list:
        found = cmp.left_only + cmp.right_only + cmp.diff_files + cmp.funny_files
        for sub in cmp.subdirs.values():
            found += _differences(sub)
        return found

    assert _differences(comparison) == []


def test_tool_reference_matches_the_server():
    from app.mcp import server as mcp_server

    tools = set(mcp_server.build_server()._tool_manager._tools)  # noqa: SLF001
    reference = (SKILL / "references" / "tools.md").read_text(encoding="utf-8")
    documented = set(re.findall(r"^\| `([a-z_]+)` \|", reference, re.M))
    assert documented == tools
    assert MCP_URL in reference
