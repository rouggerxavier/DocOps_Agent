import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight, Info, Map, Sparkles, X } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useOnboarding } from './OnboardingContext'
import type { OnboardingSectionView, OnboardingStepView } from '@/api/client'

function findFirstPendingStep(section: OnboardingSectionView): OnboardingStepView | null {
  return section.steps.find((s) => s.completed_at === null) ?? null
}

interface SectionIntroProps {
  sectionId: string
  className?: string
}

const TOUR_SECTIONS = new Set(['ingest', 'chat', 'artifacts'])

export function SectionIntro({ sectionId, className }: SectionIntroProps) {
  const { state, postEvent, isPending, startTour } = useOnboarding()
  const [dismissed, setDismissed] = useState(false)

  if (dismissed || !state || state.tour.completed || state.tour.skipped) return null

  const section = state.sections.find((s) => s.id === sectionId)
  if (!section || section.skipped) return null

  const step = findFirstPendingStep(section)
  if (!step) return null

  const isManual = step.completion_mode === 'manual'

  function handleEntendi() {
    void postEvent({
      event_type: 'step_completed',
      step_id: step!.id,
      section_id: sectionId,
      metadata: { trigger: 'manual' },
    })
    setDismissed(true)
  }

  function handleSkipSection() {
    void postEvent({ event_type: 'section_skipped', section_id: sectionId })
    setDismissed(true)
  }

  function handleDismissLocal() {
    setDismissed(true)
  }

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -8 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
        className={cn(
          'relative overflow-hidden rounded-xl border border-[color:var(--ui-accent)]/25 bg-[color:var(--ui-accent-soft)] px-4 py-4 sm:px-5',
          className,
        )}
      >
        {/* Fundo decorativo */}
        <div className="pointer-events-none absolute -right-10 -top-10 h-32 w-32 rounded-full bg-[color:var(--ui-accent)]/10 blur-2xl" />

        {/* Botão fechar */}
        <button
          type="button"
          onClick={handleDismissLocal}
          className="absolute right-3 top-3 flex h-7 w-7 items-center justify-center rounded-lg text-[color:var(--ui-text-dim)] transition-colors hover:bg-[color:var(--ui-surface-2)] hover:text-[color:var(--ui-text)]"
          aria-label="Dispensar intro"
        >
          <X className="h-3.5 w-3.5" />
        </button>

        <div className="relative flex items-start gap-3 pr-6">
          <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-[color:var(--ui-accent)]/20">
            {step.premium ? (
              <Sparkles className="h-3.5 w-3.5 text-amber-300" />
            ) : (
              <Info className="h-3.5 w-3.5 text-[color:var(--ui-accent)]" />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-[color:var(--ui-text)]">{step.title}</p>
            <p className="mt-0.5 text-xs leading-relaxed text-[color:var(--ui-text-dim)]">
              {step.description}
            </p>

            <div className="mt-3 flex flex-wrap items-center gap-2">
              {isManual && (
                <Button
                  type="button"
                  size="sm"
                  disabled={isPending}
                  onClick={handleEntendi}
                  className="h-7 bg-[color:var(--ui-accent)] px-3 text-[11px] text-[color:var(--ui-bg)] hover:bg-[color:var(--ui-accent-strong)]"
                >
                  Entendi
                </Button>
              )}

              {!isManual && step.next_hint && (
                <Button
                  variant="ghost"
                  size="sm"
                  asChild
                  className="h-7 px-3 text-[11px] text-[color:var(--ui-accent)]"
                >
                  <Link to={`/${step.next_hint.section}`}>
                    Ir para próxima etapa
                    <ChevronRight className="h-3 w-3" />
                  </Link>
                </Button>
              )}

              <button
                type="button"
                disabled={isPending}
                onClick={handleSkipSection}
                className="text-[11px] text-[color:var(--ui-text-meta)] transition-colors hover:text-[color:var(--ui-text-dim)]"
              >
                Pular seção
              </button>

              {TOUR_SECTIONS.has(sectionId) && (
                <button
                  type="button"
                  onClick={() => startTour(sectionId)}
                  className="ml-auto flex items-center gap-1 text-[11px] text-[color:var(--ui-accent)] transition-colors hover:text-[color:var(--ui-accent-strong)]"
                >
                  <Map className="h-3 w-3" />
                  Me mostra com tour
                </button>
              )}
            </div>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  )
}
