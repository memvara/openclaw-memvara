"""Gates for the native OpenClaw plugin.

HTTP MCP is declared in the manifest. This package must not look like a
capture plugin.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "memvara"
HOSTED = "https://app.memvara.dev/mcp"
REPO_NAME = "memvara/openclaw-memvara"


def _json(path: pathlib.Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _library_bytes(sha: str, path: str) -> bytes:
    root = os.environ.get("MEMVARA_LIBRARY")
    if root:
        return subprocess.check_output(
            ["git", "-C", root, "show", f"{sha}:{path}"],
        )
    import urllib.request
    url = f"https://raw.githubusercontent.com/memvara/memvara/{sha}/{path}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read()


def _lock() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / "skill.lock").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


class Manifest(unittest.TestCase):
    def test_http_mcp_not_stdio(self) -> None:
        body = _json(ROOT / "openclaw.plugin.json")
        assert isinstance(body, dict)
        self.assertEqual(body["id"], "memvara")
        self.assertNotEqual(body.get("kind"), "memory")
        server = body["mcpServers"]["memvara"]
        self.assertEqual(server["url"], HOSTED)
        self.assertEqual(server["transport"], "streamable-http")
        self.assertNotIn("command", server)

    def test_package_is_not_a_tool_echo(self) -> None:
        pkg = _json(ROOT / "package.json")
        self.assertEqual(pkg["name"], "@memvara/openclaw-memvara")
        src = (ROOT / "index.js").read_text(encoding="utf-8")
        self.assertIn("register()", src)
        self.assertNotIn("defineToolPlugin", src)
        self.assertNotIn("kind\": \"memory\"", (ROOT / "openclaw.plugin.json").read_text())


class SkillTree(unittest.TestCase):
    def test_skill_has_front_matter_and_references(self) -> None:
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.splitlines()[0] == "---")
        named = set(re.findall(r"references/([a-z0-9-]+\.md)", text))
        self.assertTrue(named)
        for name in named:
            self.assertTrue((SKILL / "references" / name).is_file(), name)

    def test_matches_library_at_lock_sha(self) -> None:
        lock = _lock()
        sha = lock["sha"]
        for rel in ("SKILL.md", "references/hosted-mcp.md"):
            expected = _library_bytes(sha, f"memvara/skills/memvara/{rel}")
            self.assertEqual((SKILL / rel).read_bytes(), expected, rel)


class Hygiene(unittest.TestCase):
    def test_no_npx_in_json(self) -> None:
        for path in ROOT.rglob("*.json"):
            self.assertNotIn("npx", path.read_text(encoding="utf-8"), path)

    def test_readme(self) -> None:
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(HOSTED, text)
        self.assertIn("slots.memory", text)
        self.assertNotIn("npx ", text)

    def test_license(self) -> None:
        self.assertIn("Apache License", (ROOT / "LICENSE").read_text(encoding="utf-8"))

    def test_github_org(self) -> None:
        env = os.environ.get("GITHUB_REPOSITORY")
        if env:
            self.assertEqual(env, REPO_NAME)


if __name__ == "__main__":
    unittest.main()
