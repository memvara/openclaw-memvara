# openclaw-memvara

Give OpenClaw a memory it can prove. This is **not** a `plugins.slots.memory`
capture plugin.

OpenClaw 2026.7 starts hosted MCP from **config**, not from a Claude bundle.
The command that actually writes it (probed on 2026.7.1-2):

```
openclaw mcp add memvara --url https://app.memvara.dev/mcp --transport streamable-http --auth oauth --no-probe
openclaw mcp login memvara
```

`--no-probe` saves without connecting. `mcp login` opens the browser for Allow.

Install this package for the skill (and a native `mcpServers` declaration the
host may honor in a later OpenClaw):

```
openclaw plugins install git:github.com/memvara/openclaw-memvara
```

## Why this exists

`openclaw plugins install memvara --marketplace memvara/claude-memvara` loads
as a Claude bundle and installs the skill, but 2026.7.1-2 does not start
bundle MCP over HTTP ("stdio only today"). `mcp add` with
`transport streamable-http` is the path that writes `mcp.servers` today.

## What it does not do

- Auto-capture or auto-recall every turn
- Take `plugins.slots.memory`
- Ship `npx`, a daemon, or anything that keeps running

## Skill

`skills/memvara/` is vendored from [memvara/memvara](https://github.com/memvara/memvara).

OpenClaw exposes a skill as a user-invocable slash command by default
(`user-invocable` in the frontmatter, default `true`), so the skill is
reachable as a command here without this package shipping one.

## When the browser sign-in will not finish

The skill carries `scripts/memvara_auth.py` — inside the skill directory,
so it is `scripts/memvara_auth.py` under wherever this skill is installed.
In this repository that is `skills/memvara/scripts/memvara_auth.py`.
`openclaw plugins install` copies a plugin to `~/.openclaw/extensions/<id>`,
and this manifest declares its skill at `./skills/memvara`, so an installed
copy is under `~/.openclaw/extensions/memvara/skills/memvara/`. It is the
device-code flow, standard library only, no `pip install`, and nothing
left running when it returns. It also does `logout` and `stats`.

**Not verified on this host.** The other hosts were measured before this
was written — a probe skill pointing at a sibling file came back with the
nonce on Codex, Copilot and OpenCode, and came back empty with the skill
unregistered. On OpenClaw the skill registered (`✓ ready`, source
`openclaw-managed`) and the run could not be completed: the only model
configured here was LM Studio on `:1234`, which was not running, so the
agent turn returned `Connection error.` — a failure about the model, not
an answer about path resolution. OpenClaw also documents `{baseDir}` as
its own way for a skill to name its folder, which the vendored skill does
not use, so a relative path may or may not resolve.

Until someone runs that probe against a reachable model, give the script
an absolute path rather than trusting the agent to resolve one:

```bash
python3 ~/.openclaw/extensions/memvara/skills/memvara/scripts/memvara_auth.py authenticate
```

## Teach it your vocabulary

The built-in predicates are a personal-assistant vocabulary. A store of engineering facts
matches none of them, and an unknown predicate takes the safe default twice over:
multi-valued, so nothing supersedes it, and slow-decaying, so this morning's deploy still
ranks as fresh in two years. The first half shows up on the write receipt. The second is
silent.

Server-side configuration, so it is set where the server is launched:

```bash
MEMVARA_PREDICATES=engineering        # or: engineering,./ours.toml
```

A declaration outranks a guess, so a pack corrects a store that already classified
something wrongly rather than only shaping a fresh one.

## Coming from another memory product

```python
from memvara.compat import import_mem0, import_supermemory
```

mem0 records what changed and when, so that import rebuilds supersession. Supermemory
records current state, so its documents arrive as episodes on their original timestamps
and nothing invents a history it was never told — which means plain recall answers from
claims and looks empty until you ask for `include_episodes`. The skill says this at the
point of use.

## Other clients

Claude Code: [memvara/claude-memvara](https://github.com/memvara/claude-memvara).
A loop you wrote: `pip install memvara`.

## License

Apache-2.0.
