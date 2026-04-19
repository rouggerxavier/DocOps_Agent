import type { CSSProperties, ReactNode } from 'react'

// ── Kicker ──────────────────────────────────────────────────────────────────
export function MKicker({
  children,
  style,
}: {
  children: ReactNode
  style?: CSSProperties
}) {
  return (
    <div
      style={{
        fontFamily: "'IBM Plex Mono', 'Consolas', monospace",
        fontSize: 10,
        letterSpacing: '0.16em',
        textTransform: 'uppercase',
        color: 'var(--ui-text-meta)',
        fontWeight: 600,
        ...style,
      }}
    >
      {children}
    </div>
  )
}

// ── Chip ─────────────────────────────────────────────────────────────────────
type ChipTone = 'neutral' | 'accent' | 'warm' | 'success' | 'danger'

const CHIP_TONES: Record<ChipTone, { bg: string; fg: string; bd: string }> = {
  neutral: { bg: 'var(--ui-surface-3)', fg: 'var(--ui-text-dim)', bd: 'var(--ui-border)' },
  accent:  { bg: 'var(--ui-accent-soft)', fg: 'var(--ui-accent)', bd: 'transparent' },
  warm:    { bg: 'var(--ui-warm-soft)', fg: 'var(--ui-warm)', bd: 'transparent' },
  success: { bg: 'rgba(109,169,123,0.14)', fg: 'var(--ui-success)', bd: 'transparent' },
  danger:  { bg: 'rgba(202,111,103,0.14)', fg: 'var(--ui-danger)', bd: 'transparent' },
}

export function MChip({
  children,
  tone = 'neutral',
  size = 'md',
}: {
  children: ReactNode
  tone?: ChipTone
  size?: 'sm' | 'md'
}) {
  const c = CHIP_TONES[tone]
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: size === 'sm' ? '2px 8px' : '4px 10px',
        borderRadius: 999,
        background: c.bg,
        color: c.fg,
        fontSize: size === 'sm' ? 10 : 11,
        fontWeight: 600,
        border: `1px solid ${c.bd}`,
        whiteSpace: 'nowrap',
      }}
    >
      {children}
    </span>
  )
}

// ── Progress ──────────────────────────────────────────────────────────────────
type ProgressTone = 'accent' | 'warm' | 'success'

export function MProgress({
  value,
  tone = 'accent',
  height = 4,
}: {
  value: number
  tone?: ProgressTone
  height?: number
}) {
  const color =
    tone === 'warm'
      ? 'var(--ui-warm)'
      : tone === 'success'
        ? 'var(--ui-success)'
        : 'var(--ui-accent)'

  return (
    <div
      style={{
        height,
        background: 'var(--ui-surface-3)',
        borderRadius: 999,
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          width: `${Math.min(100, Math.max(0, value))}%`,
          height: '100%',
          background: color,
          borderRadius: 999,
          transition: 'width .4s ease',
        }}
      />
    </div>
  )
}
