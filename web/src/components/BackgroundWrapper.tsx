import { type ReactNode } from 'react'

interface BackgroundWrapperProps {
  children: ReactNode
}

export function BackgroundWrapper({ children }: BackgroundWrapperProps) {
  return (
    <div className="relative min-h-screen overflow-x-hidden bg-[#0B0E12] text-[#F3F1EB]">
      <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
        <div className="absolute inset-0 bg-[linear-gradient(180deg,#0B0E12_0%,#0E131A_18%,#0C1016_42%,#0E141C_67%,#0B0E12_100%)]" />
        <div className="absolute inset-x-0 top-[8svh] h-[26svh] bg-[linear-gradient(180deg,rgba(18,30,46,0.26),rgba(15,21,30,0.04))]" />
        <div className="absolute inset-x-0 top-[36svh] h-[28svh] bg-[linear-gradient(180deg,rgba(9,13,18,0.05),rgba(16,25,38,0.2),rgba(12,18,26,0.06))]" />
        <div className="absolute inset-x-0 top-[68svh] h-[26svh] bg-[linear-gradient(180deg,rgba(13,20,31,0.05),rgba(17,27,40,0.22),rgba(10,14,20,0.08))]" />
        <div
          className="absolute inset-0 opacity-[0.05]"
          style={{
            backgroundImage: 'radial-gradient(rgba(243,241,235,0.85) 0.45px, transparent 0.45px)',
            backgroundSize: '3px 3px',
          }}
        />
        <div
          className="absolute inset-0 opacity-[0.13]"
          style={{
            backgroundImage:
              'linear-gradient(to right, rgba(120,132,148,0.21) 1px, transparent 1px), linear-gradient(to bottom, rgba(120,132,148,0.07) 1px, transparent 1px)',
            backgroundSize: '132px 100%, 100% 132px',
            maskImage: 'linear-gradient(to bottom, transparent, black 12%, black 88%, transparent)',
          }}
        />
        <div className="absolute inset-0 bg-[radial-gradient(115%_68%_at_50%_34%,transparent_41%,rgba(0,0,0,0.38)_100%)]" />
        <div className="absolute inset-0 bg-[radial-gradient(88%_65%_at_15%_0%,rgba(47,107,255,0.09),transparent_70%)]" />
        <div className="absolute left-0 right-0 top-[35svh] h-px bg-[#27303A]/72" />
        <div className="absolute left-0 right-0 top-[56svh] h-px bg-[#27303A]/38" />
        <div className="absolute left-0 right-0 top-[72svh] h-px bg-[#27303A]/56" />
      </div>

      <div className="relative z-10">
        {children}
      </div>
    </div>
  )
}
