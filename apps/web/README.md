# GroundLoop web companion

This is the local React companion UI for GroundLoop. It does not call an LLM or upload research data. It talks only to the loopback FastAPI service started from the repository root.

## Run from the repository root

```bash
./scripts/demo.sh
```

Then open `http://127.0.0.1:5173`.

## Run the web app directly

```bash
pnpm install
pnpm dev --host 127.0.0.1
pnpm lint
pnpm exec tsc -b --noEmit
pnpm build
```

Set `VITE_GROUNDLOOP_API` only if the local API is not running at the default `http://127.0.0.1:8765`.

## Product boundary

- The UI creates Runs, profiles CSV artifacts, displays source review state, freezes evidence, renders the Convergence Map, and opens Markdown exports.
- Codex with GPT-5.6 performs literature exploration, source review, signature decomposition, alignment reasoning, and control design through the registered GroundLoop MCP server.
- Search snippets, titles, and unreviewed candidates are not evidence.
