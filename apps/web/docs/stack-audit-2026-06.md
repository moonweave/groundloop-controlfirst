# Stack audit — 2026-06

A verified survey of the open-source frontend/designer ecosystem against this starter's
stack, with upgrade verdicts. Versions confirmed against the npm registry and official
docs/changelogs as of **2026-06-21**. Re-confirm exact patch versions with
`pnpm outdated` before acting on this doc later.

## TL;DR

The stack is already current-gen — there is nothing to swap. `pnpm outdated` at audit
time showed only three drifts: `recharts` 3.8.0→3.8.1, `lucide-react` 1.20.0→1.21.0
(both applied), and `@types/node` 24→26 (**intentionally not applied** — 26 tracks Node
Current/non-LTS; we target Node 24 LTS). The real value of this audit is captured in
`AGENTS.md`: the "Reaching beyond the core" and "Do not reach for" sections, plus the
GSAP-is-now-free note and the Node baseline.

## Verdicts by layer

| Layer | Current | Verdict | Note |
|---|---|---|---|
| Build / bundler | Vite ^8 (Rolldown default) | KEEP | Vite 8 ships Rolldown (Rust) as the unified bundler; build reporter already references `rolldownOptions`. |
| Package manager | pnpm 11 | KEEP | On 11.x; single-package repo, so workspace catalogs N/A. |
| Runtime | Node | UPGRADE (baseline) | Added `engines.node >=22.12.0` + `.nvmrc` 24. Node 24 = Active LTS; 22.12 is the Vite 8 floor. |
| Language | TypeScript ~6 | KEEP (pilot 7) | TS 6 for prod. TS 7 (Go-native `tsgo`, ~10x) is at RC — pilot for CI/local typecheck only; wait for 7.1 stable before committing build-critical tooling. |
| Lint/format | ESLint 10 + typescript-eslint | KEEP | Modern flat config. Biome 2.x is a faster single-binary alternative but a lateral swap, and its type-aware rules still lag typescript-eslint. Not worth forcing here. |
| Tests | (none wired) | — | Vitest 4 is the native pick if/when tests are added. |
| Styling | Tailwind CSS v4.3 | KEEP | Oxide/Rust engine, CSS-first `@theme`, native container queries / `:has` / `color-mix`. Alternatives (Panda, UnoCSS, vanilla-extract, StyleX) are swap-candidates, not upgrades. |
| Components | shadcn/ui + Radix 1.6 | KEEP + ADD | Radix actively maintained (React 19 fixes June 2026). Add the shadcn MCP server + namespaced registries. Base UI (RC) is opt-in per greenfield. |
| Motion | Motion ^12.40 | KEEP | Unified `motion` package, `motion/react`, full React 19 support. Ensure no legacy `framer-motion` imports remain. |
| Cinematic | GSAP 3.15 + Lenis 1.3 | KEEP | **GSAP is now 100% free incl. all plugins** (Webflow). Use `useGSAP()` from `@gsap/react`. ScrollSmoother is now a free in-stack alternative to Lenis if you want one fewer dep. |
| 3D (optional) | — | ADD when needed | R3F v9 + drei 10 + three 0.184 is the React-19 line and the verified WebGL path. Spline for designer-driven scenes; Theatre.js for keyframed sequencing. |
| Charts | Recharts 3.8 | KEEP + ADD | Recharts (via shadcn `chart`) for marketing + dashboards. For data-dense/Canvas perf, add Apache ECharts — **pin `echarts-for-react@3.0.6`**. |
| Icons | Lucide 1.21 | KEEP | Add Iconify for brand/long-tail only; Tabler is a same-aesthetic catalog upgrade if Lucide's set runs short. |
| Fonts | Geist (Fontsource) | KEEP | Stay on Fontsource (self-hosted) over the new Google Fonts copy. Inter is the safe OFL alternate. |
| Design→code | — | ADD | shadcn MCP + registries (cleanest into Vite); v0 for prompt→component (lift JSX/Tailwind out of its Next scaffold); Figma Dev Mode MCP + Code Connect for handoff. |

## Avoid

- Runtime CSS-in-JS (styled-components — maintenance mode; Emotion — no RSC) in a React 19 stack.
- Tremor (dormant post-Vercel acquisition, no React 19) and Observable Plot (~16 months no release) as primary chart deps.
- `animation-timeline: scroll()` as a JS-scroll replacement — not Baseline (Safari/Firefox lag); Chromium progressive enhancement only.
- `echarts-for-react` 3.1.7 / 3.2.7 — malicious in the May 2026 "Mini Shai-Hulud" npm attack (AntV ecosystem account takeover); npm `latest` was rolled back to **3.0.6**, pin it.

## Sources

- Vite / Rolldown — https://vite.dev/blog · https://github.com/rolldown/rolldown/releases
- Tailwind v4 — https://tailwindcss.com/blog/tailwindcss-v4 · https://tailwindcss.com/blog/tailwindcss-v4-3
- shadcn/ui — https://ui.shadcn.com/docs/changelog · https://ui.shadcn.com/docs/mcp · https://ui.shadcn.com/docs/registry/namespace
- Radix / Base UI — https://www.radix-ui.com · https://base-ui.com
- Motion — https://motion.dev/docs/react · https://motion.dev/changelog
- GSAP (now free) — https://gsap.com/pricing/ · https://www.npmjs.com/package/@gsap/react
- Lenis — https://github.com/darkroomengineering/lenis
- R3F / drei / three — https://r3f.docs.pmnd.rs
- Recharts — https://recharts.org · https://ui.shadcn.com/docs/components/chart
- ECharts — https://echarts.apache.org
- Lucide / Iconify — https://lucide.dev · https://iconify.design
- Geist / Fontsource — https://vercel.com/font · https://fontsource.org
- tweakcn — https://tweakcn.com · https://github.com/jnsahaj/tweakcn
- v0 — https://v0.app
- TypeScript 7 (native) — https://devblogs.microsoft.com/typescript/
- Scroll-driven animations baseline — https://developer.mozilla.org/en-US/docs/Web/CSS/animation-timeline
- npm supply-chain (echarts-for-react / Mini Shai-Hulud, May 2026) — https://advisories.gitlab.com/npm/echarts-for-react/GMS-2026-530/ · https://www.microsoft.com/en-us/security/blog/2026/05/20/mini-shai-hulud-compromised-antv-npm-packages-enable-ci-cd-credential-theft/
