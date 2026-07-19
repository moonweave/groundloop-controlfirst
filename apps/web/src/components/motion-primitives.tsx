import { useEffect, useRef, type ReactNode } from 'react'
import {
  motion,
  useInView,
  useMotionValue,
  useScroll,
  useSpring,
} from 'motion/react'

const EASE = [0.16, 1, 0.3, 1] as const

// Thin gradient bar at the top that fills as you scroll the page.
export function ScrollProgress() {
  const { scrollYProgress } = useScroll()
  const scaleX = useSpring(scrollYProgress, {
    stiffness: 120,
    damping: 30,
    restDelta: 0.001,
  })
  return (
    <motion.div
      style={{ scaleX }}
      className="fixed inset-x-0 top-0 z-[60] h-0.5 origin-left bg-gradient-to-r from-emerald-400 to-cyan-400"
    />
  )
}

// Soft breathing glow placed behind a relative element (e.g. the featured card).
export function PulseGlow({ className }: { className?: string }) {
  return (
    <motion.div
      aria-hidden
      className={`pointer-events-none absolute -inset-0.5 -z-10 rounded-[inherit] bg-gradient-to-b from-emerald-500/40 to-cyan-500/20 blur-md ${className ?? ''}`}
      animate={{ opacity: [0.35, 0.8, 0.35] }}
      transition={{ duration: 3.5, repeat: Infinity, ease: 'easeInOut' }}
    />
  )
}

// Card wrapper with a glow that follows the cursor on hover.
export function SpotlightCard({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  const ref = useRef<HTMLDivElement>(null)
  function handleMove(e: React.MouseEvent<HTMLDivElement>) {
    const el = ref.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    el.style.setProperty('--spot-x', `${e.clientX - rect.left}px`)
    el.style.setProperty('--spot-y', `${e.clientY - rect.top}px`)
  }
  return (
    <div
      ref={ref}
      onMouseMove={handleMove}
      className={`group/spot relative h-full ${className ?? ''}`}
    >
      <div
        className="pointer-events-none absolute -inset-px z-10 rounded-xl opacity-0 transition-opacity duration-300 group-hover/spot:opacity-100"
        style={{
          background:
            'radial-gradient(240px circle at var(--spot-x) var(--spot-y), rgba(52,211,153,0.14), transparent 70%)',
        }}
      />
      {children}
    </div>
  )
}

export function Reveal({
  children,
  delay = 0,
  className,
}: {
  children: ReactNode
  delay?: number
  className?: string
}) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-80px' }}
      transition={{ duration: 0.6, delay, ease: EASE }}
    >
      {children}
    </motion.div>
  )
}

// Staggered children — wrap a grid, each direct child fades up in sequence.
export function RevealStagger({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <motion.div
      className={className}
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, margin: '-60px' }}
      variants={{
        hidden: {},
        show: { transition: { staggerChildren: 0.08 } },
      }}
    >
      {children}
    </motion.div>
  )
}

export function RevealItem({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <motion.div
      className={className}
      variants={{
        hidden: { opacity: 0, y: 24 },
        show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: EASE } },
      }}
    >
      {children}
    </motion.div>
  )
}

export function NumberTicker({
  value,
  decimals = 0,
  prefix = '',
  suffix = '',
}: {
  value: number
  decimals?: number
  prefix?: string
  suffix?: string
}) {
  const ref = useRef<HTMLSpanElement>(null)
  const inView = useInView(ref, { once: true, margin: '-50px' })
  const motionValue = useMotionValue(0)
  const spring = useSpring(motionValue, { damping: 32, stiffness: 90 })

  useEffect(() => {
    if (inView) motionValue.set(value)
  }, [inView, value, motionValue])

  useEffect(() => {
    return spring.on('change', (latest) => {
      if (ref.current) {
        ref.current.textContent =
          prefix +
          latest.toLocaleString('en-US', {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals,
          }) +
          suffix
      }
    })
  }, [spring, decimals, prefix, suffix])

  return <span ref={ref}>{`${prefix}0${suffix}`}</span>
}

export function Marquee({ children }: { children: ReactNode }) {
  return (
    <div className="relative flex w-full overflow-hidden [mask-image:linear-gradient(to_right,transparent,black_15%,black_85%,transparent)]">
      {[0, 1].map((i) => (
        <motion.div
          key={i}
          className="flex shrink-0 items-center gap-14 pr-14"
          animate={{ x: ['0%', '-100%'] }}
          transition={{ duration: 22, repeat: Infinity, ease: 'linear' }}
        >
          {children}
        </motion.div>
      ))}
    </div>
  )
}
