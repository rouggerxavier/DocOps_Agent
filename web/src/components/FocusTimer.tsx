import { useState, useEffect, useRef, useCallback } from 'react'
import { Timer, X, Play, Pause, RotateCcw, Coffee } from 'lucide-react'
import { cn } from '@/lib/utils'

// ── Types ─────────────────────────────────────────────────────────────────────

type Phase = 'focus' | 'short_break' | 'long_break'

const PHASE_DURATIONS: Record<Phase, number> = {
  focus: 25 * 60,
  short_break: 5 * 60,
  long_break: 15 * 60,
}

const PHASE_LABELS: Record<Phase, string> = {
  focus: 'Foco',
  short_break: 'Pausa curta',
  long_break: 'Pausa longa',
}

const PHASE_COLORS: Record<Phase, string> = {
  focus: 'text-blue-400',
  short_break: 'text-emerald-400',
  long_break: 'text-violet-400',
}

const PHASE_BG: Record<Phase, string> = {
  focus: 'from-blue-600/20 to-blue-600/5',
  short_break: 'from-emerald-600/20 to-emerald-600/5',
  long_break: 'from-violet-600/20 to-violet-600/5',
}

// ── SVG ring progress ─────────────────────────────────────────────────────────

function RingProgress({ progress, color }: { progress: number; color: string }) {
  const r = 54
  const circ = 2 * Math.PI * r
  const offset = circ * (1 - progress)
  return (
    <svg width="128" height="128" className="absolute inset-0">
      <circle cx="64" cy="64" r={r} fill="none" stroke="#27272a" strokeWidth="6" />
      <circle
        cx="64" cy="64" r={r} fill="none"
        stroke="currentColor"
        strokeWidth="6"
        strokeDasharray={circ}
        strokeDashoffset={offset}
        strokeLinecap="round"
        className={cn('transition-all duration-1000', color)}
        style={{ transform: 'rotate(-90deg)', transformOrigin: '50% 50%' }}
      />
    </svg>
  )
}

// ── Mini timer (collapsed, shown in corner) ───────────────────────────────────

function MiniTimer({
  running,
  timeLeft,
  phase,
  onClick,
}: {
  running: boolean
  timeLeft: number
  phase: Phase
  onClick: () => void
}) {
  const m = Math.floor(timeLeft / 60).toString().padStart(2, '0')
  const s = (timeLeft % 60).toString().padStart(2, '0')
  return (
    <button
      onClick={onClick}
      className={cn(
        'flex items-center gap-2 rounded-xl border border-zinc-700 bg-zinc-900/95 px-3 py-2 text-xs font-mono font-semibold shadow-lg backdrop-blur-sm transition-all hover:border-zinc-500',
        PHASE_COLORS[phase],
      )}
    >
      {running
        ? <Timer className="h-3.5 w-3.5 animate-pulse" />
        : <Coffee className="h-3.5 w-3.5" />
      }
      {m}:{s}
    </button>
  )
}

// ── Main FocusTimer ───────────────────────────────────────────────────────────

interface FocusTimerProps {
  onClose: () => void
}

export function FocusTimer({ onClose }: FocusTimerProps) {
  const [expanded, setExpanded] = useState(true)
  const [phase, setPhase] = useState<Phase>('focus')
  const [timeLeft, setTimeLeft] = useState(PHASE_DURATIONS.focus)
  const [running, setRunning] = useState(false)
  const [sessions, setSessions] = useState(0)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const total = PHASE_DURATIONS[phase]
  const progress = timeLeft / total

  const tick = useCallback(() => {
    setTimeLeft(t => {
      if (t <= 1) {
        setRunning(false)
        if (phase === 'focus') {
          setSessions(s => s + 1)
          // notify
          if ('Notification' in window && Notification.permission === 'granted') {
            new Notification('DocOps — Sessão concluída!', {
              body: sessions + 1 >= 4 ? 'Hora da pausa longa!' : 'Hora de uma pausa curta.',
            })
          }
        }
        return 0
      }
      return t - 1
    })
  }, [phase, sessions])

  useEffect(() => {
    if (running) {
      intervalRef.current = setInterval(tick, 1000)
    } else if (intervalRef.current) {
      clearInterval(intervalRef.current)
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [running, tick])

  function switchPhase(p: Phase) {
    setRunning(false)
    setPhase(p)
    setTimeLeft(PHASE_DURATIONS[p])
  }

  function reset() {
    setRunning(false)
    setTimeLeft(PHASE_DURATIONS[phase])
  }

  const m = Math.floor(timeLeft / 60).toString().padStart(2, '0')
  const s = (timeLeft % 60).toString().padStart(2, '0')

  if (!expanded) {
    return (
      <div className="fixed bottom-6 right-6 z-50">
        <MiniTimer running={running} timeLeft={timeLeft} phase={phase} onClick={() => setExpanded(true)} />
      </div>
    )
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 w-72 rounded-2xl border border-zinc-800 bg-zinc-950/95 shadow-2xl backdrop-blur-md overflow-hidden">
      {/* Header */}
      <div className={cn('flex items-center justify-between px-4 py-3 bg-gradient-to-r', PHASE_BG[phase])}>
        <div className="flex items-center gap-2">
          <Timer className={cn('h-4 w-4', PHASE_COLORS[phase])} />
          <span className="text-xs font-semibold text-zinc-200">Modo Foco</span>
          {sessions > 0 && (
            <span className="ml-1 rounded-full bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-400">
              {sessions} {sessions === 1 ? 'sessão' : 'sessões'}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setExpanded(false)}
            className="rounded p-1 text-zinc-500 hover:text-zinc-300 transition-colors"
            title="Minimizar"
          >
            <Timer className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={onClose}
            className="rounded p-1 text-zinc-500 hover:text-red-400 transition-colors"
            title="Fechar"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Phase tabs */}
      <div className="flex border-b border-zinc-800">
        {(['focus', 'short_break', 'long_break'] as Phase[]).map(p => (
          <button
            key={p}
            onClick={() => switchPhase(p)}
            className={cn(
              'flex-1 py-2 text-[10px] font-medium transition-colors',
              phase === p ? cn(PHASE_COLORS[p], 'border-b-2 border-current') : 'text-zinc-600 hover:text-zinc-400',
            )}
          >
            {PHASE_LABELS[p]}
          </button>
        ))}
      </div>

      {/* Timer */}
      <div className="flex flex-col items-center py-6">
        <div className="relative flex h-32 w-32 items-center justify-center">
          <RingProgress progress={progress} color={PHASE_COLORS[phase]} />
          <div className="text-center">
            <span className={cn('text-3xl font-bold font-mono tabular-nums', PHASE_COLORS[phase])}>
              {m}:{s}
            </span>
            <p className="text-[10px] text-zinc-600 mt-0.5">{PHASE_LABELS[phase]}</p>
          </div>
        </div>

        {/* Controls */}
        <div className="mt-5 flex items-center gap-3">
          <button
            onClick={reset}
            className="rounded-full border border-zinc-800 p-2 text-zinc-500 hover:border-zinc-600 hover:text-zinc-300 transition-colors"
          >
            <RotateCcw className="h-4 w-4" />
          </button>
          <button
            onClick={() => setRunning(r => !r)}
            className={cn(
              'flex h-12 w-12 items-center justify-center rounded-full border-2 transition-all',
              running
                ? 'border-zinc-600 bg-zinc-800 text-zinc-200 hover:bg-zinc-700'
                : cn('border-current bg-current/10 hover:bg-current/20', PHASE_COLORS[phase]),
            )}
          >
            {running
              ? <Pause className="h-5 w-5 text-zinc-200" />
              : <Play className={cn('h-5 w-5 ml-0.5', PHASE_COLORS[phase])} />
            }
          </button>
          <button
            onClick={() => {
              const next: Phase = phase === 'focus'
                ? sessions > 0 && sessions % 4 === 0 ? 'long_break' : 'short_break'
                : 'focus'
              switchPhase(next)
            }}
            className="rounded-full border border-zinc-800 p-2 text-zinc-500 hover:border-zinc-600 hover:text-zinc-300 transition-colors"
            title="Pular fase"
          >
            <Coffee className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Tip */}
      <div className="border-t border-zinc-800 px-4 py-2">
        <p className="text-[10px] text-zinc-700 text-center">
          {phase === 'focus'
            ? 'Mantenha o foco. Evite distrações por 25 min.'
            : 'Levante, respire, hidrate-se.'}
        </p>
      </div>
    </div>
  )
}

// ── Trigger button (shown in layout) ─────────────────────────────────────────

export function FocusTimerTrigger({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-zinc-200"
      title="Modo Foco"
    >
      <Timer className="h-3.5 w-3.5 shrink-0" />
      Foco
    </button>
  )
}
