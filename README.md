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

## Other clients

Claude Code: [memvara/claude-memvara](https://github.com/memvara/claude-memvara).
A loop you wrote: `pip install memvara`.

## License

Apache-2.0.
