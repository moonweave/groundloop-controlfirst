# AGENTS.md — frontend-stack

Agent protocol for this repo. Single source of truth for how to work here. `CLAUDE.md` points to this file.

## What this is

Reusable frontend starter — no project-specific code, just the stack wired up and proven. The `Helix` landing page in `src/App.tsx` is **demo content** showing the stack's range; swap it out per project.

## Stack (all free / OSS — do not swap)

- Build / dev / HMR: **Vite + pnpm**
- Framework: **React 19 + TypeScript**
- Styling: **Tailwind CSS v4** (`@import "tailwindcss";` is the first line of `src/index.css`)
- Components: **shadcn/ui** (Radix-based, code you own) — see `components.json` (style `radix-nova`, baseColor `neutral`, alias `@/components/ui`)
- Motion: **Motion**
- Charts: **Recharts** (via shadcn `chart`)
- Icons: **Lucide**
- Font: **Geist** (Fontsource)

Need something outside this list? **Ask before adding a dependency.** For verified per-project add-ons (designer blocks, theming, data-dense charts) and the full stack rationale + sources, see [`docs/stack-audit-2026-06.md`](./docs/stack-audit-2026-06.md).

## Commands

- Node **24 LTS** recommended (`.nvmrc`); **22.12+** is the floor (Vite 8 requirement)
- `corepack enable pnpm` — if pnpm is missing (corepack ships with Node)
- `pnpm install` — install (pnpm only; a `pnpm-lock.yaml` is committed)
- `pnpm dev` — dev server at http://localhost:5173
- `pnpm build` — production build (`tsc -b && vite build`)
- `pnpm exec tsc -b --noEmit` — typecheck only
- `pnpm lint` — ESLint
- `pnpm dlx shadcn@latest add <name> --yes` — add a UI component

## Rules

- Use only the stack above. A new library → ask first.
- **Animations: reuse `src/components/motion-primitives.tsx`** — `Reveal`, `RevealStagger`, `RevealItem`, `NumberTicker`, `Marquee`, `ScrollProgress`, `SpotlightCard`, `PulseGlow`. Add new primitives there, not ad hoc.
- **Cinematic scroll (GSAP + Lenis): `src/components/cinematic.tsx`.** GSAP is now 100% free incl. all plugins (ScrollTrigger, ScrollSmoother, SplitText, MorphSVG) — use them via the `useGSAP()` hook from `@gsap/react`.
- New UI components via the shadcn CLI above — don't hand-roll Radix wrappers.
- Before declaring done: `pnpm exec tsc -b --noEmit` **and** `pnpm build` must pass.

## Gotchas

- **`resolve.dedupe: ['react', 'react-dom']` in `vite.config.ts` is required.** Without it, pnpm's nested `node_modules` gives Motion two React copies and it crashes (`Cannot read properties of null (reading 'useContext')`). **Never remove it.**
- **lucide-react has no brand icons** (`Github` / `Twitter` / `Linkedin` are missing) — use generic icons.
- shadcn CLI `init -b` flag is the component base (`radix` | `base`), not a base color.

## Reaching beyond the core (per-project — ask first, don't bake into this base)

The core stack stays fixed. When a project genuinely needs more, these are the verified mid-2026 picks — install per-project, prefer the shadcn CLI:

- **Designer blocks** (MIT, shadcn-registry installable): [Magic UI](https://magicui.design) + [Cult UI](https://www.cult-ui.com) for landing/marketing; [Kibo UI](https://www.kibo-ui.com) for dashboard widgets (Gantt/Kanban/Table). All use the same `motion` package as this stack.
- **Theming**: [tweakcn](https://tweakcn.com) (Apache-2.0) — visual editor for shadcn + Tailwind v4 themes; exports OKLCH CSS vars into `src/index.css`.
- **AI component install**: shadcn MCP server — `pnpm dlx shadcn@latest mcp init --client claude`. Private/team component sources go in `components.json` → `registries`.
- **Data-dense charts**: Recharts (core) covers marketing + dashboard charts. For high-volume Canvas perf only, add Apache ECharts — **pin `echarts-for-react@3.0.6`** (versions 3.1.7 / 3.2.7 were malicious in the May 2026 "Mini Shai-Hulud" npm attack; npm `latest` was rolled back to 3.0.6).
- **Long-tail / brand icons**: Lucide stays default; add [Iconify](https://iconify.design) (`@iconify/react`) only for brand logos and one-off glyphs Lucide lacks.
- **Alternate font**: Geist stays default; Inter (`@fontsource-variable/inter`, OFL) is the safe neutral alternate. Keep fonts on Fontsource (self-hosted), not Google Fonts.
- **New-project component base**: Radix stays the default. Base UI is the convergence successor (Radix + Floating UI + MUI) and shadcn dual-supports it, but it's still `1.0.0-rc` — opt in per greenfield project, don't migrate existing work.

## Do not reach for

- **Runtime CSS-in-JS** (styled-components is in maintenance mode; Emotion has no RSC support) in a React 19 stack.
- **Tremor** (dormant after the Vercel acquisition, no React 19) or **Observable Plot** (no release in ~16 months) as primary chart deps.
- Native `animation-timeline: scroll()` as a replacement for the JS scroll stack — still not Baseline (Safari/Firefox lag). Use it only as a Chromium progressive enhancement behind `@supports`.
- **`@types/node` 26** — that tracks Node 26 (Current/non-LTS). Stay on the `24` line to match the Node 24 LTS target.
