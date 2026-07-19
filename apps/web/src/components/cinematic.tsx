import { useEffect, useRef } from 'react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { useGSAP } from '@gsap/react'
import Lenis from 'lenis'

gsap.registerPlugin(ScrollTrigger, useGSAP)

// Deterministic pseudo-random so stars are stable across renders.
function pseudo(n: number) {
  const x = Math.sin(n * 12.9898) * 43758.5453
  return x - Math.floor(x)
}

const STARS_FAR = Array.from({ length: 48 }, (_, i) => ({
  left: pseudo(i + 1) * 100,
  top: pseudo(i + 13) * 70,
  size: pseudo(i + 7) * 1.6 + 1,
  dur: 2 + pseudo(i + 9) * 3,
  delay: pseudo(i + 2) * 4,
  base: 0.35 + pseudo(i + 3) * 0.4,
}))

const STARS_NEAR = Array.from({ length: 14 }, (_, i) => ({
  left: pseudo(i + 30) * 100,
  top: pseudo(i + 41) * 70,
  size: pseudo(i + 19) * 2 + 2,
  dur: 1.8 + pseudo(i + 23) * 2.5,
  delay: pseudo(i + 17) * 3,
}))

const BUILDINGS = [
  { left: 3, w: 7, h: 55 },
  { left: 12, w: 6, h: 80 },
  { left: 20, w: 8, h: 62 },
  { left: 30, w: 5, h: 95 },
  { left: 38, w: 9, h: 70 },
  { left: 49, w: 6, h: 88 },
  { left: 58, w: 8, h: 58 },
  { left: 68, w: 5, h: 100 },
  { left: 76, w: 9, h: 66 },
  { left: 87, w: 7, h: 82 },
]

// Lenis smooth scroll, driven by GSAP's ticker and synced to ScrollTrigger.
// eslint-disable-next-line react-refresh/only-export-components
export function useSmoothScroll() {
  useEffect(() => {
    const lenis = new Lenis({ duration: 1.1 })
    lenis.on('scroll', ScrollTrigger.update)
    const onRaf = (time: number) => lenis.raf(time * 1000)
    gsap.ticker.add(onRaf)
    gsap.ticker.lagSmoothing(0)
    return () => {
      lenis.destroy()
      gsap.ticker.remove(onRaf)
    }
  }, [])
}

export function Cinematic() {
  const root = useRef<HTMLDivElement>(null)

  useGSAP(
    () => {
      const tl = gsap.timeline({
        scrollTrigger: {
          trigger: root.current,
          start: 'top top',
          end: 'bottom bottom',
          scrub: 1,
        },
      })

      // Rise: star layers drift at different speeds (depth parallax).
      tl.to('.cine-stars-far', { yPercent: -35, duration: 1, ease: 'none' }, 0)
      tl.to('.cine-stars-near', { yPercent: -75, duration: 1, ease: 'none' }, 0)
      tl.fromTo(
        '.cine-planet',
        { yPercent: 65, scale: 0.55 },
        { yPercent: -8, scale: 1.15, duration: 1, ease: 'none' },
        0,
      )

      // Sky cross-fades: space -> dawn -> day.
      tl.to('.cine-dawn', { opacity: 1, duration: 0.4, ease: 'none' }, 0.12)
      tl.to('.cine-stars-far', { opacity: 0, duration: 0.3, ease: 'none' }, 0.38)
      tl.to('.cine-stars-near', { opacity: 0, duration: 0.25, ease: 'none' }, 0.36)
      tl.to('.cine-day', { opacity: 1, duration: 0.35, ease: 'none' }, 0.58)

      // City skyline rises at the landing.
      tl.fromTo(
        '.cine-city',
        { yPercent: 100 },
        { yPercent: 0, duration: 0.4, ease: 'power2.out' },
        0.58,
      )

      // Text steps hand off one to the next.
      tl.to('.cine-step-1', { opacity: 0, y: -30, duration: 0.2, ease: 'none' }, 0.16)
      tl.fromTo(
        '.cine-step-2',
        { opacity: 0, y: 30 },
        { opacity: 1, y: 0, duration: 0.22, ease: 'none' },
        0.3,
      )
      tl.to('.cine-step-2', { opacity: 0, y: -30, duration: 0.2, ease: 'none' }, 0.56)
      tl.fromTo(
        '.cine-step-3',
        { opacity: 0, y: 30 },
        { opacity: 1, y: 0, duration: 0.24, ease: 'none' },
        0.72,
      )
    },
    { scope: root },
  )

  return (
    <section ref={root} className="relative h-[320vh] bg-black">
      <div className="cine-stage sticky top-0 flex h-screen items-center justify-center overflow-hidden">
        {/* Sky layers */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_50%_120%,#0b1220,#000)]" />
        <div className="cine-dawn absolute inset-0 opacity-0 bg-gradient-to-b from-indigo-950 via-purple-950 to-emerald-950" />
        <div className="cine-day absolute inset-0 opacity-0 bg-gradient-to-b from-sky-950 via-emerald-900 to-emerald-700" />

        {/* Far stars + shooting stars */}
        <div className="cine-stars-far absolute inset-0">
          {STARS_FAR.map((s, i) => (
            <span
              key={i}
              className="cine-twinkle absolute rounded-full bg-white"
              style={{
                left: `${s.left}%`,
                top: `${s.top}%`,
                width: s.size,
                height: s.size,
                opacity: s.base,
                animation: `twinkle ${s.dur.toFixed(2)}s ease-in-out ${s.delay.toFixed(2)}s infinite`,
              }}
            />
          ))}
          {[0, 1].map((i) => (
            <span
              key={`shoot-${i}`}
              className="cine-shoot absolute h-px w-24 bg-gradient-to-r from-white via-white/70 to-transparent"
              style={{
                top: `${i === 0 ? 14 : 24}%`,
                left: `${i === 0 ? 6 : 28}%`,
                animation: `shoot ${9 + i * 4}s ease-in ${3 + i * 5}s infinite`,
              }}
            />
          ))}
        </div>

        {/* Near stars (faster parallax, brighter) */}
        <div className="cine-stars-near absolute inset-0">
          {STARS_NEAR.map((s, i) => (
            <span
              key={i}
              className="cine-twinkle absolute rounded-full bg-white shadow-[0_0_6px_1px] shadow-white/40"
              style={{
                left: `${s.left}%`,
                top: `${s.top}%`,
                width: s.size,
                height: s.size,
                animation: `twinkle ${s.dur.toFixed(2)}s ease-in-out ${s.delay.toFixed(2)}s infinite`,
              }}
            />
          ))}
        </div>

        {/* Planet (atmosphere + surface shading + orbiting satellite) */}
        <div className="cine-planet absolute size-[440px]">
          <div className="absolute -inset-10 rounded-full bg-emerald-400/20 blur-3xl" />
          <div className="absolute inset-0 overflow-hidden rounded-full bg-gradient-to-br from-emerald-400 via-emerald-500 to-cyan-600 shadow-[0_0_140px_-10px] shadow-emerald-500/60">
            <div className="absolute inset-0 rounded-full bg-[radial-gradient(circle_at_32%_28%,rgba(255,255,255,0.5),transparent_46%)]" />
            <div className="absolute inset-0 rounded-full bg-[radial-gradient(circle_at_78%_82%,rgba(0,0,0,0.5),transparent_55%)]" />
          </div>
          <div
            className="cine-orbit absolute -inset-20"
            style={{ animation: 'orbitspin 16s linear infinite' }}
          >
            <span className="absolute left-1/2 top-0 size-2.5 -translate-x-1/2 rounded-full bg-white shadow-[0_0_10px_2px] shadow-white/50" />
          </div>
        </div>

        {/* City skyline */}
        <div className="cine-city absolute inset-x-0 bottom-0 h-[42%]">
          {BUILDINGS.map((b, i) => (
            <div
              key={i}
              className="absolute bottom-0 rounded-t-sm bg-gradient-to-t from-black to-emerald-950/80"
              style={{ left: `${b.left}%`, width: `${b.w}%`, height: `${b.h}%` }}
            />
          ))}
        </div>

        {/* Text steps (stacked, cross-faded by the timeline) */}
        <div className="relative z-10 mx-auto max-w-2xl px-6 text-center">
          <p className="cine-step-1 text-balance text-4xl font-semibold tracking-tight text-white sm:text-6xl">
            It starts in the noise.
          </p>
          <p className="cine-step-2 absolute inset-x-0 top-0 text-balance text-4xl font-semibold tracking-tight text-white opacity-0 sm:text-6xl">
            A signal rises.
          </p>
          <p className="cine-step-3 absolute inset-x-0 top-0 text-balance text-4xl font-semibold tracking-tight text-white opacity-0 sm:text-6xl">
            And lands on your desk.
          </p>
        </div>

        <span className="absolute bottom-6 left-1/2 -translate-x-1/2 text-xs uppercase tracking-widest text-white/40">
          scroll
        </span>
      </div>
    </section>
  )
}
