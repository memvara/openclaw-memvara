"""Gates for the native OpenClaw plugin.

HTTP MCP is declared in the manifest. This package must not look like a
capture plugin.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import ssl
import subprocess
import sys
import unittest
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "memvara"
HOSTED = "https://app.memvara.dev/mcp"
REPO_NAME = "memvara/openclaw-memvara"


def _json(path: pathlib.Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


class LibraryUnreachable(Exception):
    """Neither a local checkout nor GitHub could answer. Raised, never swallowed.

    A drift check that quietly passes when it cannot look is the same as no drift check.
    This repository has already been caught by exactly that shape: `skill-sync.yml` failed
    on every scheduled run for days while nothing here went red, because the vendored copy
    and `skill.lock` stayed consistent with each other and the only thing that would have
    noticed was a scheduled job nobody read.
    """


def _trust() -> "ssl.SSLContext":
    """A context that trusts the same roots `curl` does.

    python.org's macOS build ignores the system trust store, so an unqualified `urlopen`
    raises CERTIFICATE_VERIFY_FAILED against a certificate `curl` accepts. Without this the
    drift check below does not fail on a Mac -- it *skips*, reporting the library as
    unreachable when the library is fine, which is the quiet half of the failure it was
    written to catch.
    """
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "memvara-tests"})
    with urllib.request.urlopen(request, timeout=30, context=_trust()) as resp:
        return bytes(resp.read())


def _library_bytes(sha: str, path: str) -> bytes:
    root = os.environ.get("MEMVARA_LIBRARY")
    if root:
        try:
            return subprocess.check_output(
                ["git", "-C", root, "show", f"{sha}:{path}"],
                stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            # The checkout has the sha `skill.lock` names and nothing else: CI clones the
            # library AT that sha, shallow, so the library's current HEAD is simply not an
            # object here. Falling back to the network rather than failing is what lets the
            # drift check below run on CI at all -- and it only matters when the lock is
            # stale, which is precisely when the check has something to say.
            pass
    return _fetch(f"https://raw.githubusercontent.com/memvara/memvara/{sha}/{path}")


def _library_head() -> str:
    """The library default branch's current sha, or raise `LibraryUnreachable`."""
    root = os.environ.get("MEMVARA_LIBRARY")
    if root:
        for ref in ("origin/main", "main"):
            try:
                return subprocess.check_output(
                    ["git", "-C", root, "rev-parse", ref],
                    stderr=subprocess.DEVNULL).decode().strip()
            except subprocess.CalledProcessError:
                continue
    try:
        body = _fetch("https://api.github.com/repos/memvara/memvara/commits/main")
        return str(json.loads(body)["sha"])
    except Exception as exc:
        raise LibraryUnreachable(str(exc)) from exc


def _library_skill_files(sha: str) -> "set[str]":
    """Every path under the packaged skill at `sha`, relative to it."""
    root = os.environ.get("MEMVARA_LIBRARY")
    prefix = "memvara/skills/memvara/"
    if root:
        try:
            out = subprocess.check_output(
                ["git", "-C", root, "ls-tree", "-r", "--name-only", sha,
                 "memvara/skills/memvara"], stderr=subprocess.DEVNULL).decode()
        except subprocess.CalledProcessError:
            # Not an object in this checkout -- see `_library_bytes`. Ask GitHub instead
            # of reporting the library unreachable, which would SKIP the check on the one
            # run that needed it.
            out = None
        if out is not None:
            return {line[len(prefix):] for line in out.splitlines()
                    if line.startswith(prefix)}
    try:
        tree = json.loads(_fetch(
            f"https://api.github.com/repos/memvara/memvara/git/trees/{sha}?recursive=1"))
    except Exception as exc:
        raise LibraryUnreachable(str(exc)) from exc
    return {entry["path"][len(prefix):] for entry in tree.get("tree", [])
            if entry.get("type") == "blob" and entry["path"].startswith(prefix)}


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
        """The name is derived from the manifest, not written out.

        This line used to pin the literal `@memvara/openclaw-memvara`, and that is how a
        real defect survived two releases: the package name and the plugin id disagreed,
        every `openclaw plugins install` ended in `Config validation failed`, and this
        guard held the wrong value in place while agreeing with the file it was checking.
        A claim and its guard frozen together, both wrong -- which this repository's own
        CLAUDE.md names as its signature failure.
        """
        pkg = _json(ROOT / "package.json")
        manifest = _json(ROOT / "openclaw.plugin.json")
        self.assertEqual(pkg["name"], f"@memvara/{manifest['id']}")
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

    def test_the_vendored_skill_is_not_behind_the_library(self) -> None:
        """The whole tree, against the library's CURRENT default branch.

        `test_matches_library_at_lock_sha` cannot catch a stale sync and is not supposed
        to: it compares the copy against the sha the copy itself names, so a lock and a
        tree frozen together agree with each other forever. That is exactly how this repo
        shipped a skill five commits behind -- `skill-sync.yml` dying every night on a
        permission the organization pins, nothing here going red, and the agreement
        between the two stale files being the thing that hid it.

        Two deliberate choices about noise. It compares BYTES rather than shas, so the
        library moving does not fail this repository -- only the library's *skill* moving
        does, which is rare. And it compares the file SET as well, because a new reference
        file upstream is drift that a per-file comparison of the files we already have
        would never see.

        When the library cannot be reached this SKIPS rather than passes. A skip is
        visible in the run output; a pass is not, and a check that silently succeeds when
        it could not look is the failure it exists to prevent, one level up.
        """
        try:
            head = _library_head()
            upstream = _library_skill_files(head)
        except LibraryUnreachable as exc:
            raise unittest.SkipTest(
                f"library unreachable, drift NOT checked: {exc}") from exc

        self.assertTrue(upstream, "the library reported an empty skill tree")
        ours = {str(path.relative_to(SKILL))
                for path in SKILL.rglob("*") if path.is_file()}
        self.assertEqual(
            ours, upstream,
            f"the vendored skill's file set differs from the library at {head[:7]} — "
            "run scripts/sync_plugin_repos.py from the library and update skill.lock")

        drifted = []
        for rel in sorted(upstream):
            expected = _library_bytes(head, f"memvara/skills/memvara/{rel}")
            if (SKILL / rel).read_bytes() != expected:
                drifted.append(rel)
        self.assertEqual(
            drifted, [],
            f"vendored skill is behind memvara/memvara@{head[:7]}: {drifted} — "
            "sync it")


class SharedInstructions(unittest.TestCase):
    """CLAUDE.md is shared across every plugin repo, and nothing used to carry it.

    It was hand-copied and it drifted: eleven of fourteen sections were byte-identical
    across all seven repositories while a section written in one of them reached none of
    the others. The canonical is `plugin-claude.md` in the library; `skill-sync.yml`
    composes this file from it and preserves the `local:` block, because two sections
    legitimately differ per repo — a repository's own runtime facts, and hook rules that
    only one plugin needs.

    Without this guard the sync would be a tidier way to drift rather than an end to it,
    which is the objection the section it carries makes about hand-maintained copies.
    """

    BEGIN = "<!-- local: begin"
    END = "<!-- local: end -->"

    def _text(self) -> str:
        return (ROOT / "CLAUDE.md").read_text(encoding="utf-8")

    def test_the_local_block_is_delimited_exactly_once(self) -> None:
        """Two of either marker and the splice takes the wrong span; none and the composer
        refuses rather than replacing this repository's sections with a placeholder.
        """
        text = self._text()
        self.assertEqual(text.count(self.BEGIN), 1)
        self.assertEqual(text.count(self.END), 1)
        self.assertLess(text.index(self.BEGIN), text.index(self.END))

    def test_the_shared_half_matches_the_library(self) -> None:
        """Compared against the LIBRARY, never against this file's own halves.

        A check that read both halves of one file would prove it internally consistent and
        nothing else — exactly how a vendored skill sat five commits behind while its own
        drift test passed.
        """
        lock = _lock()
        try:
            canonical = _library_bytes(lock["sha"], "plugin-claude.md").decode("utf-8")
        except Exception as exc:  # noqa: BLE001
            raise unittest.SkipTest(
                f"library has no plugin-claude.md at {lock['sha'][:7]}: {exc}") from exc
        text = self._text()
        head, rest = text.split(self.BEGIN, 1)
        _, tail = rest.split(self.END, 1)
        want_head, want_tail = canonical.split("@@LOCAL@@\n", 1)
        self.assertEqual(head, want_head,
                         "text above the local block drifted — edit plugin-claude.md in "
                         "memvara/memvara, not the copy here")
        self.assertEqual(tail.lstrip("\n"), want_tail.lstrip("\n"),
                         "text below the local block drifted from plugin-claude.md")

    def test_the_local_block_holds_what_only_this_repo_knows(self) -> None:
        """Not decorative: it carries the two sections that differ per repo. A sync that
        flattened it would lose them silently — the file would still read as a complete
        CLAUDE.md, just one belonging to a different repository.
        """
        local = self._text().split(self.BEGIN, 1)[1].split(self.END, 1)[0]
        self.assertIn("Runtime facts that cost hours to find", local)
        self.assertIn("If this repo ships hooks", local)


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


class Version(unittest.TestCase):
    """Every version this repository states must be the same one, and none may hide.

    Five skill syncs shipped under 0.1.0. The vendored skill is the whole of what a client
    receives here, it changed five times, and the string a client compares never moved.
    `claude-memvara` was caught by the identical shape at larger scale -- twenty-one
    commits on main behind an unchanged version, `/plugin update` answering "already at
    the latest version" for every one of them.

    Three deliberate choices, each of them paid for by a sabotage run.

    Files are found by walking the tree, not by reading a list, so a manifest nobody
    remembered cannot go unchecked. `DECLARED` is then the completeness half -- it names
    the manifests that MUST carry a version, and it is compared against the walk in both
    directions, which is what keeps a hand-written list from quietly narrowing coverage.

    The file set comes from `git ls-files`, not from the filesystem. Two sweeps of the
    tree were tried first and both were wrong in a way a passing run could not show: one
    ignored directories by absolute path, which excluded the entire repository whenever the
    checkout was a worktree (those live under `.claude/worktrees/`, so `.claude` was in the
    parts of every path); the next was caught by CI dragging in six manifests from the
    library checkout under `_library/`. Git already knows which files this repository owns.

    And the assertions demand presence rather than absence of the wrong value. The
    coverage check was first written as a bare set comparison and passed on that broken
    walk because both sides were empty; the value check alone still passes when one
    manifest of several drops its version entirely. A guard an absence satisfies has
    stopped guarding.
    """

    VERSION = "0.2.5"
    DECLARED = {
        'openclaw.plugin.json',
        'package.json',
    }

    @classmethod
    def _walk(cls, node: object, where: str = ""):
        """Every `version` string at any depth, with the pointer that reached it."""
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "version" and isinstance(value, str):
                    yield f"{where}.{key}", value
                else:
                    yield from cls._walk(value, f"{where}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                yield from cls._walk(value, f"{where}[{index}]")

    @classmethod
    def _candidates(cls) -> list:
        """Every JSON file this repository TRACKS -- asked of git, not of the filesystem.

        The filesystem is the wrong referent. CI checks the library out into `_library/`,
        which carries the sibling plugins' own manifests, and an `rglob` swept all six into
        the walk; a denylist would then have to grow a name for every scratch directory
        anyone ever creates, and the first one nobody thought of is a false failure. What
        the question actually means is "files this repository owns", and git is the thing
        that knows. Untracked checkouts and nested worktrees fall out for free.

        No fallback when git cannot answer. A fallback here would silently cover less than
        the caller believes, which is the failure this whole class exists to prevent.
        """
        listed = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z", "*.json"],
            check=True, capture_output=True, text=True).stdout
        return [
            ROOT / name for name in listed.split("\0")
            if name and pathlib.PurePath(name).name != "package-lock.json"
        ]

    def _stated(self) -> list:
        found = []
        for path in self._candidates():
            try:
                body = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                continue
            found.extend((path, where, value) for where, value in self._walk(body))
        return found

    def test_every_version_this_repo_states_is_the_released_one(self) -> None:
        stated = self._stated()
        self.assertTrue(
            stated, "no file states a version at all -- this guard has stopped guarding")
        for path, where, value in stated:
            self.assertEqual(
                value, self.VERSION,
                f"{path.relative_to(ROOT)}{where} says {value!r}; a partial bump is how a "
                "client gets told it is current while the contents moved underneath it")

    def test_exactly_the_manifests_that_must_declare_a_version_do(self) -> None:
        """Both directions, because each catches a mistake the other cannot see.

        A file the walk misses is a version nobody checks. A file that has stopped
        declaring one is a manifest shipping unversioned -- invisible to the value check
        above, which goes green as soon as any other file still says the right thing.
        Confirmed by sabotage: deleting the key from one of three manifests left it green.
        """
        reached = {str(path.relative_to(ROOT)) for path, _where, _value in self._stated()}
        by_text = {
            str(path.relative_to(ROOT)) for path in self._candidates()
            if '"version"' in path.read_text(encoding="utf-8")
        }
        self.assertEqual(by_text, self.DECLARED, "a manifest gained or lost its version")
        self.assertEqual(reached, self.DECLARED, "the JSON walk missed a stated version")

    def test_the_release_number_is_written_down_exactly_once_in_this_suite(self) -> None:
        """`VERSION` above is the only place the tests name it.

        Ported from claude-memvara, which learned it the same way this repository just
        did: another test asserted the release literally, so a bump had to be applied in
        two places and one of them was missed. Every extra place is the mechanism a
        partial bump needs, and a partial bump is what tells a client it is current while
        the contents moved underneath it.

        The duplicates that prompted this now read `Version.VERSION` instead, which is
        why they no longer count.
        """
        source = pathlib.Path(__file__).read_text(encoding="utf-8")
        self.assertEqual(
            source.count(f'"{self.VERSION}"'), 1,
            f"{self.VERSION} appears more than once in this file; VERSION is meant to be "
            "the single place the suite states the release")


def _readme_prose(root: pathlib.Path) -> str:
    """The README with every run of whitespace collapsed to one space.

    Where prose wraps is not a fact about what it says. Matching raw text pins a line
    break, so a reflow turns a guard red while the sentence is present and correct -- and
    it lets a rewrapped reintroduction slip past `assertNotIn`.
    """
    return " ".join(root.joinpath("README.md").read_text(encoding="utf-8").split())


class ModuleShape(unittest.TestCase):
    """Nothing may be defined below `unittest.main()`.

    Measured in the sibling repos: a class appended after the `__main__` block is
    collected by `unittest discover` and NOT by `python3 test/test_plugin.py`, and both
    print OK -- 26 tests one way and 21 the other, with nothing saying so. A passing run
    must not be able to mean "the check never ran".
    """

    def test_nothing_is_defined_after_the_main_block(self) -> None:
        import ast

        body = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8")).body
        guards = [i for i, node in enumerate(body)
                  if isinstance(node, ast.If) and "__main__" in ast.dump(node.test)]
        self.assertEqual(len(guards), 1, "expected exactly one __main__ block")
        after = [type(node).__name__ for node in body[guards[0] + 1:]]
        self.assertEqual(
            after, [],
            f"{after} is defined after `unittest.main()`, so "
            "`python3 test/test_plugin.py` runs without it and still prints OK")


class AuthScript(unittest.TestCase):
    """The skill carries the device-code flow, and this host is the one that was not
    measured.

    Codex, Copilot and OpenCode were each probed before the design relied on them: a skill
    whose SKILL.md held no nonce and pointed at a sibling file returned the nonce, and
    returned nothing with the registration removed and the files still on disk. On OpenClaw
    the skill REGISTERED (`openclaw skills list` showed it ready, source
    `openclaw-managed`) and the turn could not run -- the only configured model was LM
    Studio on `:1234` and it was not listening, so the agent returned `Connection error.`
    That is a failure about the model and not an answer about path resolution, so no
    verdict is recorded in either direction.

    It matters more here than elsewhere because OpenClaw documents `{baseDir}` as its own
    way for a skill to name its folder, and the vendored skill does not use it. So the
    README gives an absolute path rather than trusting the agent to resolve a relative
    one, and these tests hold it to saying that the question is open.
    """

    SCRIPT = SKILL / "scripts" / "memvara_auth.py"
    COMMANDS = ("authenticate", "login", "logout", "stats")

    def test_the_skill_ships_the_auth_script(self) -> None:
        """Positive, because the failure to catch is a deletion."""
        self.assertTrue(
            self.SCRIPT.is_file(),
            f"{self.SCRIPT.relative_to(ROOT)} is missing; the README tells the user it "
            "is there")

    def test_the_script_runs_here_and_names_every_command(self) -> None:
        """Executed rather than read, on the interpreter running this suite. A byte diff
        against the library cannot see a broken script: a library that shipped one hands
        every repo two copies that are equally broken and agree."""
        done = subprocess.run(
            [sys.executable, str(self.SCRIPT), "not-a-command"],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        for command in self.COMMANDS:
            self.assertIn(command, done.stdout,
                          f"the usage this prints omits {command}")

    def test_the_readme_gives_a_path_that_does_not_need_resolving(self) -> None:
        """The absolute form, because the relative one is exactly what is unverified here.

        Asserted and then RESOLVED against this checkout for the in-repo path, so a README
        naming a plausible path into the wrong directory fails rather than sending someone
        nowhere.
        """
        text = _readme_prose(ROOT)
        in_repo = "skills/memvara/scripts/memvara_auth.py"
        self.assertIn(in_repo, text)
        self.assertTrue((ROOT / in_repo).is_file(),
                        f"the README says {in_repo}, and nothing is there")
        # Built from the manifest rather than written out, because the first version of
        # this guard string-matched a path nobody had checked and passed on the wrong one.
        # `~/.openclaw/skills` is the MANAGED skills directory -- where the throwaway
        # probe was placed by hand during measurement, which is what made it look right --
        # while `openclaw plugins install` copies to `~/.openclaw/extensions/<id>` (the
        # host's own docs/tools/plugin.md). A home directory cannot be resolved in CI, but
        # the claim still has a referent: the manifest says where the skill sits inside
        # the plugin, so the README's path has to be that, under the install root.
        # The install directory is `package.json`'s name, NOT the plugin manifest's `id`.
        # They differ here -- id is `memvara`, the package is `@memvara/openclaw-memvara`
        # -- and the host uses the package name: an end-to-end install landed at
        # `~/.openclaw/extensions/openclaw-memvara/`, from a source directory called
        # something else entirely, so it is not the source name either.
        #
        # This line has now been wrong twice. First it named the MANAGED skills directory,
        # `~/.openclaw/skills/`, where the throwaway probe had been placed by hand. Then a
        # review "fixed" it to the manifest id, which was a value computed from a file
        # rather than a fact read off the host. Both looked right and neither was, because
        # nobody had installed the plugin and looked until the end-to-end run.
        manifest = _json(ROOT / "openclaw.plugin.json")
        package = _json(ROOT / "package.json")
        declared = manifest["skills"][0].lstrip("./")
        where = str(package["name"]).rsplit("/", 1)[-1]
        expected = f"~/.openclaw/extensions/{where}/{declared}/scripts/memvara_auth.py"
        self.assertIn(expected, text,
                      f"the README should give the installed path {expected}; a reader "
                      "whose plugin is installed otherwise has no path that resolves")
        self.assertIn("no `pip install`", text)

    def test_the_package_name_and_the_plugin_id_agree(self) -> None:
        """The host requires it, and refuses the install when they differ.

        `openclaw plugins install` names the extension directory from `package.json` and
        then writes a config entry keyed by that name, which is validated against the
        plugin manifest's `id`. Until 0.2.5 the two disagreed -- id `memvara`, package
        `@memvara/openclaw-memvara` -- and every install ended in
        `Config validation failed: plugins.entries.openclaw-memvara: plugin not found`,
        leaving `plugins` absent from `openclaw.json`. `openclaw doctor` said so plainly:
        `WARN memvara: plugin id mismatch`.

        The plugin still loaded, which is why this survived two releases and was found
        only by installing the published artifact and reading the output. Nothing in this
        repository could see it: both files were internally consistent, and it is the
        relationship BETWEEN them that the host cares about.
        """
        manifest = _json(ROOT / "openclaw.plugin.json")
        package = _json(ROOT / "package.json")
        self.assertEqual(
            str(package["name"]).rsplit("/", 1)[-1], manifest["id"],
            "package.json's name and the manifest id must agree, or `openclaw plugins "
            "install` writes a config entry the host then rejects")

    def test_the_readme_gives_an_install_command_this_host_accepts(self) -> None:
        """Measured against openclaw 2026.2.14, because the shipped one did not work.

        `openclaw plugins install git:github.com/...` answers `unsupported npm spec:
        protocol specs are not allowed`; installing the release zip answers `extracted
        package missing package.json`; and the npm name in package.json is not published.
        The host's own docs list a path, a tarball, a zip or an npm package -- no git URL.
        A local directory is the only form that works.

        Both directions: the working form must be present AND the form that fails must be
        gone, so this cannot be satisfied by a README that stops saying how to install.
        """
        text = _readme_prose(ROOT)
        self.assertIn("openclaw plugins install ./memvara", text,
                      "the README does not give an install command this host accepts")
        self.assertNotIn("plugins install git:", text,
                         "the README still gives the git spec, which this host refuses")

    def test_the_readme_says_the_probe_did_not_run_here(self) -> None:
        """The honest half, and the one a later reader will most want.

        Stated positively -- the admission must be PRESENT -- because "the README does not
        claim it works" is satisfied by a README that says nothing at all, and silence
        here reads as verified. It names the reason too, so the next person knows the
        probe is worth re-running rather than that the host is broken.
        """
        text = _readme_prose(ROOT)
        self.assertIn("Not verified on this host", text)
        self.assertIn("Connection error", text,
                      "the README does not say WHY it is unverified, so a reader cannot "
                      "tell a blocked measurement from a negative result")

    def test_the_readme_no_longer_says_no_python_ships(self) -> None:
        """It listed "a local Python process" under what this does not do, and one ships.

        Both directions, against normalised prose so a rewrapped reintroduction is caught:
        the false item must be gone AND the true half -- that nothing keeps running -- must
        still be there.
        """
        text = _readme_prose(ROOT)
        self.assertNotIn("local Python process", text,
                         "the README still lists a local Python process among what this "
                         "does not ship, and skills/memvara/scripts/ holds one")
        self.assertIn("or anything that keeps running", text)


if __name__ == "__main__":
    unittest.main()
