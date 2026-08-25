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
        """No JSON *this repo ships* may reach for npx.

        `_library` is skipped because it is not ours: CI checks the library out there, at
        `skill.lock`'s sha, so the drift test can run offline. The moment that lock moves
        to a sha where the library has an npm package, an unfiltered scan reads
        `_library/npm/memvara/package.json` -- whose description legitimately begins "npx
        memvara" -- and fails a sync PR for a string in another repository. That is not
        hypothetical: it happened in claude-memvara on 2026-08-25, and this lock bump is
        the one that would have done it here.

        The scan stays repo-wide rather than narrowing to `plugin/`: the rule is about
        anything shipped from here, and an allowlist of directories stops covering the
        next one added.
        """
        for path in ROOT.rglob("*.json"):
            if {"node_modules", "_library"} & set(path.parts):
                continue
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
