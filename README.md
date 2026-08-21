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
- Ship `npx` or a local Python process

## Skill

`skills/memvara/` is vendored from [memvara/memvara](https://github.com/memvara/memvara).

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
