import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Bot, FileText, MessageSquare, ScrollText, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useOnboarding } from './OnboardingContext'

const TOTAL_FRAMES = 3

const SLIDE_VARIANTS = {
  enter: (dir: number) => ({ x: dir > 0 ? 40 : -40, opacity: 0 }),
  center: { x: 0, opacity: 1 },
  exit: (dir: number) => ({ x: dir > 0 ? -40 : 40, opacity: 0 }),
}

function DotIndicator({ total, current }: { total: number; current: number }) {
  return (
    <div className="flex items-center gap-1.5">
      {Array.from({ length: total }, (_, i) => (
        <span
          key={i}
          className={cn(
            'block rounded-full transition-all duration-300',
            i === current
              ? 'h-2 w-5 bg-[color:var(--ui-accent)]'
              : 'h-2 w-2 bg-[color:var(--ui-surface-3)]',
          )}
        />
      ))}
    </div>
  )
}

function Frame1() {
  return (
    <div className="flex flex-col items-center gap-6 px-2 py-4 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-[color:var(--ui-accent-soft)]">
        <Bot className="h-8 w-8 text-[color:var(--ui-accent)]" />
      </div>
      <div>
        <h2 className="font-headline text-2xl font-extrabold leading-tight text-[color:var(--ui-text)] sm:text-3xl">
          Oi, eu sou o DocOps&nbsp;Agent.
        </h2>
        <p className="mt-3 max-w-sm text-sm leading-relaxed text-[color:var(--ui-text-dim)] sm:text-base">
          Seu assistente de estudos com IA que lê seus documentos e responde com citação — sem inventar nada.
        </p>
      </div>
    </div>
  )
}

function Frame2() {
  const steps = [
    {
      icon: FileText,
      color: 'text-[color:var(--ui-accent)] bg-[color:var(--ui-accent-soft)]',
      title: 'Insira documentos',
      sub: 'PDF, Markdown, TXT, URL ou foto',
    },
    {
      icon: MessageSquare,
      color: 'text-amber-300 bg-amber-500/10',
      title: 'Converse com IA',
      sub: 'Perguntas respondidas com grounding e citação',
    },
    {
      icon: ScrollText,
      color: 'text-emerald-300 bg-emerald-500/10',
      title: 'Salve artefatos',
      sub: 'Resumo, checklist, notas e plano de estudo',
    },
  ]

  return (
    <div className="px-2 py-4">
      <h2 className="mb-6 text-center font-headline text-2xl font-extrabold text-[color:var(--ui-text)] sm:text-3xl">
        Como funciono em&nbsp;30s
      </h2>
      <div className="space-y-3">
        {steps.map((step, i) => (
          <div key={step.title} className="flex items-center gap-4 rounded-xl border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-2)] px-4 py-3">
            <div className={cn('flex h-9 w-9 shrink-0 items-center justify-center rounded-lg', step.color)}>
              <step.icon className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-[color:var(--ui-text)]">
                <span className="mr-2 text-[color:var(--ui-text-meta)]">{i + 1}.</span>
                {step.title}
              </p>
              <p className="mt-0.5 text-xs text-[color:var(--ui-text-dim)]">{step.sub}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function Frame3({ onStart, onExplore, isPending }: { onStart: () => void; onExplore: () => void; isPending: boolean }) {
  return (
    <div className="flex flex-col items-center gap-6 px-2 py-4 text-center">
      <div className="pointer-events-none absolute -right-20 -top-20 h-48 w-48 rounded-full bg-[color:var(--ui-accent-soft)] blur-3xl opacity-60" />
      <div className="relative">
        <h2 className="font-headline text-2xl font-extrabold text-[color:var(--ui-text)] sm:text-3xl">
          Vamos começar?
        </h2>
        <p className="mt-3 max-w-sm text-sm leading-relaxed text-[color:var(--ui-text-dim)]">
          Posso te guiar pelas seções em alguns minutos, ou você explora no seu ritmo.
        </p>
      </div>
      <div className="relative flex w-full flex-col gap-3 sm:flex-row">
        <Button
          type="button"
          disabled={isPending}
          onClick={onStart}
          className="flex-1 bg-[color:var(--ui-accent)] text-[color:var(--ui-bg)] hover:bg-[color:var(--ui-accent-strong)]"
        >
          Quero um tour rápido
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={isPending}
          onClick={onExplore}
          className="flex-1 border-[color:var(--ui-border-strong)] text-[color:var(--ui-text-dim)] hover:text-[color:var(--ui-text)]"
        >
          Explorar sozinho
        </Button>
      </div>
    </div>
  )
}

export function WelcomeModal() {
  const { state, postEvent, isPending } = useOnboarding()
  const [frame, setFrame] = useState(0)
  const [direction, setDirection] = useState(1)
  const [dismissed, setDismissed] = useState(false)
  const overlayRef = useRef<HTMLDivElement>(null)
  const closeButtonRef = useRef<HTMLButtonElement>(null)

  const shouldShow =
    !dismissed &&
    !!state &&
    !state.tour.welcome_seen &&
    !state.tour.skipped

  // Auto-focus close button when modal opens
  useEffect(() => {
    if (shouldShow) {
      closeButtonRef.current?.focus()
    }
  }, [shouldShow])

  // Close on ESC
  useEffect(() => {
    if (!shouldShow) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') handleDismiss()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shouldShow])

  if (!shouldShow) return null

  function navigate(delta: number) {
    setDirection(delta)
    setFrame((f) => Math.min(Math.max(f + delta, 0), TOTAL_FRAMES - 1))
  }

  function handleDismiss() {
    setDismissed(true)
    void postEvent({ event_type: 'welcome_shown' })
  }

  function handleStart() {
    void postEvent({ event_type: 'tour_started' }).then(() =>
      postEvent({ event_type: 'welcome_shown' }),
    )
    setDismissed(true)
  }

  function handleExplore() {
    void postEvent({ event_type: 'welcome_shown' })
    setDismissed(true)
  }

  function handleOverlayClick(e: React.MouseEvent<HTMLDivElement>) {
    if (e.target === overlayRef.current) handleDismiss()
  }

  const isLastFrame = frame === TOTAL_FRAMES - 1

  return (
    <div
      ref={overlayRef}
      role="dialog"
      aria-modal="true"
      aria-label="Bem-vindo ao DocOps Agent"
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm"
      onClick={handleOverlayClick}
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.95, opacity: 0 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
        className="relative flex w-full max-w-md flex-col overflow-hidden rounded-2xl border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface)] shadow-2xl"
        style={{ maxHeight: 'min(90svh, 640px)' }}
      >
        {/* Close button */}
        <button
          ref={closeButtonRef}
          type="button"
          onClick={handleDismiss}
          className="absolute right-4 top-4 z-10 flex h-8 w-8 items-center justify-center rounded-lg text-[color:var(--ui-text-dim)] transition-colors hover:bg-[color:var(--ui-surface-2)] hover:text-[color:var(--ui-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--ui-accent)]"
          aria-label="Fechar"
        >
          <X className="h-4 w-4" />
        </button>

        {/* Frame content */}
        <div className="min-h-[220px] flex-1 overflow-y-auto px-6 pt-8 pb-6">
          <AnimatePresence mode="wait" custom={direction}>
            <motion.div
              key={frame}
              custom={direction}
              variants={SLIDE_VARIANTS}
              initial="enter"
              animate="center"
              exit="exit"
              transition={{ duration: 0.22, ease: 'easeInOut' }}
            >
              {frame === 0 && <Frame1 />}
              {frame === 1 && <Frame2 />}
              {frame === 2 && (
                <Frame3 onStart={handleStart} onExplore={handleExplore} isPending={isPending} />
              )}
            </motion.div>
          </AnimatePresence>
        </div>

        {/* Bottom nav */}
        <div className="flex shrink-0 items-center justify-between border-t border-[color:var(--ui-border-soft)] px-6 py-4">
          <DotIndicator total={TOTAL_FRAMES} current={frame} />
          <div className="flex items-center gap-2">
            {frame > 0 && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => navigate(-1)}
                className="h-8 px-3 text-xs text-[color:var(--ui-text-dim)]"
              >
                Voltar
              </Button>
            )}
            {!isLastFrame && (
              <Button
                type="button"
                size="sm"
                onClick={() => navigate(1)}
                className="h-8 bg-[color:var(--ui-accent)] px-4 text-xs text-[color:var(--ui-bg)] hover:bg-[color:var(--ui-accent-strong)]"
              >
                Próximo
              </Button>
            )}
          </div>
        </div>
      </motion.div>
    </div>
  )
}
