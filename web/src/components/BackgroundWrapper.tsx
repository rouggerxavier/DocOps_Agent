import { type ReactNode } from 'react'

interface BackgroundWrapperProps {
  children: ReactNode
}

export function BackgroundWrapper({ children }: BackgroundWrapperProps) {
  return (
    <div className="relative min-h-screen overflow-x-hidden bg-[color:var(--ui-bg)] text-[color:var(--ui-text)]">
      <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(78%_54%_at_78%_10%,rgba(201,139,94,0.13),transparent_60%),radial-gradient(58%_42%_at_18%_14%,rgba(244,240,232,0.08),transparent_68%),linear-gradient(180deg,#0E1012_0%,#121518_48%,#0E1012_100%)]" />
        <div
          className="absolute inset-0 opacity-[0.055]"
          style={{
            backgroundImage: 'radial-gradient(rgba(244,240,232,0.9) 0.55px, transparent 0.55px)',
            backgroundSize: '5px 5px',
            maskImage: 'linear-gradient(to bottom, transparent, black 12%, black 88%, transparent)',
          }}
        />
        <div className="absolute inset-0 bg-[radial-gradient(72%_56%_at_50%_46%,transparent_46%,rgba(0,0,0,0.36)_100%)]" />
        <div className="absolute left-[10%] right-[10%] top-24 h-px bg-[linear-gradient(90deg,transparent,rgba(255,255,255,0.08),transparent)]" />
        <div className="absolute bottom-[-18svh] right-[-10vw] h-[42svh] w-[42svh] rounded-full bg-[rgba(201,139,94,0.08)] blur-3xl" />
      </div>

      <div className="relative z-10">{children}</div>
    </div>
  )
}
