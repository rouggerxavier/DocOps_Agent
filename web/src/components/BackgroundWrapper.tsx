import type { ReactNode } from 'react'

interface BackgroundWrapperProps {
  children: ReactNode
  /** Slot for future animated background (e.g. Three.js canvas) */
  animatedLayer?: ReactNode
}

export function BackgroundWrapper({ children, animatedLayer }: BackgroundWrapperProps) {
  return (
    <div className="relative min-h-screen overflow-x-hidden bg-zinc-950 text-zinc-100">
      {/* Background layer — z-0, behind all content */}
      <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
        {/* Static gradients + glow orbs */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_80%_50%_at_50%_-10%,rgba(59,130,246,0.12),transparent)]" />
        <div className="absolute -top-60 -left-60 h-[800px] w-[800px] rounded-full bg-blue-600/10 blur-[160px]" />
        <div className="absolute top-1/3 -right-40 h-[600px] w-[600px] rounded-full bg-violet-600/10 blur-[140px]" />
        <div className="absolute -bottom-40 left-1/3 h-[500px] w-[500px] rounded-full bg-blue-500/8 blur-[120px]" />
        {/* Dot grid */}
        <div
          className="absolute inset-0 opacity-[0.022]"
          style={{ backgroundImage: 'radial-gradient(circle, #a1a1aa 1px, transparent 1px)', backgroundSize: '32px 32px' }}
        />
        {/* Future animated layer (Three.js, particles, etc.) renders here */}
        {animatedLayer}
      </div>

      {/* Content layer — z-10, above background */}
      <div className="relative z-10">
        {children}
      </div>
    </div>
  )
}
