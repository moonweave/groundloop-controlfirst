# frontend-stack

Free / open-source frontend stack starter. A reusable base for landing pages, dashboards, and SaaS UIs — no project-specific code, just the stack wired up and proven.

The `Helix` landing page in `src/App.tsx` is **demo content** showing the stack's range; swap it out per project.

## Stack (all free / OSS)

| Layer | Tool |
|---|---|
| Build / dev / HMR | Vite, pnpm |
| Framework | React 19 + TypeScript |
| Styling | Tailwind CSS v4 |
| Components | shadcn/ui (Radix-based, code you own) |
| Motion | Motion |
| Charts | Recharts (via shadcn `chart`) |
| Icons | Lucide |
| Font | Geist (Fontsource) |

Optional free add-ons: **Magic UI / Aceternity** (copy-paste flashy components), **tweakcn** (theme-token editor).

## Getting started

```bash
pnpm install
pnpm dev      # http://localhost:5173
pnpm build    # production build
```

## Reusable bits

`src/components/motion-primitives.tsx` is project-agnostic — copy it anywhere:

- `Reveal`, `RevealStagger`, `RevealItem` — scroll-triggered fade-up (staggered)
- `NumberTicker` — count-up on view
- `Marquee` — infinite logo/row scroller
- `ScrollProgress` — top gradient progress bar
- `SpotlightCard` — cursor-following glow on hover
- `PulseGlow` — breathing glow behind a featured element

## Recreate from scratch

```bash
pnpm create vite@latest my-app --template react-ts
cd my-app && pnpm install
pnpm add tailwindcss @tailwindcss/vite motion recharts lucide-react
pnpm add -D @types/node
# vite.config.ts: tailwindcss() plugin + '@'->src alias + resolve.dedupe ['react','react-dom']
# src/index.css first line: @import "tailwindcss";
pnpm dlx shadcn@latest init -d -b radix --yes
pnpm dlx shadcn@latest add button card badge accordion separator avatar sheet chart --yes
```

## Gotchas

- **`resolve.dedupe: ['react', 'react-dom']` in `vite.config.ts` is required** — without it, pnpm's nested `node_modules` gives Motion two React copies and it crashes (`Cannot read properties of null (reading 'useContext')`).
- **lucide-react has no brand icons** (`Github`/`Twitter`/`Linkedin` are missing) — use generic icons.
- shadcn CLI `init -b` flag is component base (`radix` | `base`), not a base color.
