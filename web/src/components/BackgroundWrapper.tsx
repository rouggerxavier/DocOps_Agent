import { useRef, useEffect, useState, type ReactNode } from 'react'

interface BackgroundWrapperProps {
  children: ReactNode
  /** Slot for animated background (e.g. Three.js canvas) */
  animatedLayer?: ReactNode
}

export function BackgroundWrapper({ children, animatedLayer }: BackgroundWrapperProps) {
  const orb1Ref = useRef<HTMLDivElement>(null)
  const orb2Ref = useRef<HTMLDivElement>(null)
  const orb3Ref = useRef<HTMLDivElement>(null)
  const [interactive, setInteractive] = useState(false)

  // Desktop + no reduced-motion → enable cursor glow & orb parallax
  useEffect(() => {
    const mqSize = window.matchMedia('(min-width: 768px)')
    const mqMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setInteractive(mqSize.matches && !mqMotion.matches)
    update()
    mqSize.addEventListener('change', update)
    mqMotion.addEventListener('change', update)
    return () => {
      mqSize.removeEventListener('change', update)
      mqMotion.removeEventListener('change', update)
    }
  }, [])

  // Cursor glow + orb drift/parallax — all ref-based, zero re-renders
  useEffect(() => {
    if (!interactive) return

    const mouse = { x: 0, y: 0 }
    const smooth = { x: 0, y: 0 }
    let raf = 0

    const onMove = (e: MouseEvent) => {
      mouse.x = e.clientX
      mouse.y = e.clientY
    }
    window.addEventListener('mousemove', onMove, { passive: true })

    const animate = () => {
      const lerp = 0.06
      smooth.x += (mouse.x - smooth.x) * lerp
      smooth.y += (mouse.y - smooth.y) * lerp

      // Normalized mouse position (-1 to 1) for orb parallax
      const nx = (smooth.x / window.innerWidth - 0.5) * 2
      const ny = (smooth.y / window.innerHeight - 0.5) * 2

      // Orb organic drift (multi-frequency, no CSS keyframes conflict)
      const t = performance.now() * 0.001
      const d1x = Math.sin(t * 0.05) * 18 + Math.cos(t * 0.03) * 10
      const d1y = Math.cos(t * 0.04) * 14 + Math.sin(t * 0.06) * 7
      const d2x = Math.sin(t * 0.04 + 1.2) * -22 + Math.cos(t * 0.06 + 2) * 10
      const d2y = Math.cos(t * 0.05 + 1.5) * 16 + Math.sin(t * 0.03 + 3) * -9
      const d3x = Math.sin(t * 0.03 + 2.4) * 14 + Math.cos(t * 0.05 + 1) * -7
      const d3y = Math.cos(t * 0.06 + 3.2) * 11 + Math.sin(t * 0.04 + 2) * 13

      // Combine drift + mouse parallax per orb
      if (orb1Ref.current) {
        orb1Ref.current.style.transform = `translate(${d1x + nx * 15}px, ${d1y + ny * 10}px)`
      }
      if (orb2Ref.current) {
        orb2Ref.current.style.transform = `translate(${d2x + nx * -12}px, ${d2y + ny * -8}px)`
      }
      if (orb3Ref.current) {
        orb3Ref.current.style.transform = `translate(${d3x + nx * 8}px, ${d3y + ny * 12}px)`
      }

      raf = requestAnimationFrame(animate)
    }
    raf = requestAnimationFrame(animate)

    return () => {
      window.removeEventListener('mousemove', onMove)
      cancelAnimationFrame(raf)
      // Reset inline transforms so CSS animations can resume on mode change
      ;[orb1Ref, orb2Ref, orb3Ref].forEach(ref => {
        if (ref.current) ref.current.style.transform = ''
      })
    }
  }, [interactive])

  return (
    <div className="relative min-h-screen overflow-x-hidden bg-zinc-950 text-zinc-100">
      {/* Background layer — z-0, behind all content */}
      <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
        {/* Static radial gradient */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_80%_50%_at_50%_-10%,rgba(59,130,246,0.12),transparent)]" />

        {/* Glow orbs — CSS drift on mobile, JS drift+parallax on desktop */}
        <div
          ref={orb1Ref}
          className="orb-drift-1 absolute -top-60 -left-60 h-[800px] w-[800px] rounded-full bg-blue-600/10 blur-[160px]"
        />
        <div
          ref={orb2Ref}
          className="orb-drift-2 absolute top-1/3 -right-40 h-[600px] w-[600px] rounded-full bg-violet-600/10 blur-[140px]"
        />
        <div
          ref={orb3Ref}
          className="orb-drift-3 absolute -bottom-40 left-1/3 h-[500px] w-[500px] rounded-full bg-blue-500/8 blur-[120px]"
        />

        {/* Dot grid */}
        <div
          className="absolute inset-0 opacity-[0.035]"
          style={{ backgroundImage: 'radial-gradient(circle, #a1a1aa 1px, transparent 1px)', backgroundSize: '32px 32px' }}
        />

        {/* Animated layer (Three.js particles) */}
        {animatedLayer}

        {/* Hero readability mask — recalibrated: tighter ellipse, lighter opacity */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_50%_45%_at_50%_30%,rgba(9,9,11,0.50),transparent_70%)]" />

      </div>

      {/* Content layer — z-10, above background */}
      <div className="relative z-10">
        {children}
      </div>
    </div>
  )
}
