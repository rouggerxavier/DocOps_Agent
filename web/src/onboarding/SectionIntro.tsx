import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ChevronRight, Info, Map, Sparkles, X } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useOnboarding } from './OnboardingContext'
import { useCapabilities, type EntitlementCapabilityKey } from '@/features/CapabilitiesProvider'
import { trackUpgradeInitiated } from '@/features/premiumAnalytics'
import type { OnboardingSectionView, OnboardingStepView } from '@/api/client'

const PREMIUM_STEP_CAPABILITIES: Partial<Record<string, EntitlementCapabilityKey>> = {
  'chat.memory': 'premium_personalization',
  'artifacts.premium_templates': 'premium_artifact_templates',
}

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
  const capabilities = useCapabilities()
  const navigate = useNavigate()
  const [dismissed, setDismissed] = useState(false)

  if (dismissed || !state || state.tour.completed || state.tour.skipped) return null

  const section = state.sections.find((s) => s.id === sectionId)
  if (!section || section.skipped) return null

  const step = findFirstPendingStep(section)
  if (!step) return null

  const isManual = step.completion_mode === 'manual'
  const capKey = step.premium ? PREMIUM_STEP_CAPABILITIES[step.id] : undefined
  const isLocked = Boolean(
    step.premium && capabilities.entitlementsEnabled && capKey && !capabilities.hasCapability(capKey),
  )

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

  function handleUnlockIntent() {
    void postEvent({
      event_type: 'upgrade_intent_from_onboarding',
      step_id: step!.id,
      section_id: sectionId,
      metadata: { premium_cta: step!.id },
    })
    trackUpgradeInitiated({ touchpoint: 'onboarding.premium_step', metadata: { step_id: step!.id } })
    void navigate('/settings')
  }

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -8 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
        className={cn(
          'relative overflow-hidden rounded-xl border px-4 py-4 sm:px-5',
          isLocked
            ? 'border-amber-500/30 bg-amber-900/10'
            : 'border-[color:var(--ui-accent)]/25 bg-[color:var(--ui-accent-soft)]',
          className,
        )}
      >
        {/* Fundo decorativo */}
        <div
          className={cn(
            'pointer-events-none absolute -right-10 -top-10 h-32 w-32 rounded-full blur-2xl',
            isLocked ? 'bg-amber-500/8' : 'bg-[color:var(--ui-accent)]/10',
          )}
        />

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
          <div
            className={cn(
              'mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg',
              isLocked ? 'bg-amber-500/20' : 'bg-[color:var(--ui-accent)]/20',
            )}
          >
            {step.premium ? (
              <Sparkles className="h-3.5 w-3.5 text-amber-300" />
            ) : (
              <Info className="h-3.5 w-3.5 text-[color:var(--ui-accent)]" />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <p className="text-sm font-semibold text-[color:var(--ui-text)]">{step.title}</p>
              {isLocked && (
                <span className="shrink-0 rounded-full bg-amber-500/20 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-amber-300">
                  Pro
                </span>
              )}
            </div>
            <p className="mt-0.5 text-xs leading-relaxed text-[color:var(--ui-text-dim)]">
              {step.description}
            </p>

            <div className="mt-3 flex flex-wrap items-center gap-2">
              {isLocked ? (
                <>
                  <Button
                    type="button"
                    size="sm"
                    onClick={handleUnlockIntent}
                    className="h-7 border border-amber-500/40 bg-amber-500/15 px-3 text-[11px] text-amber-200 hover:bg-amber-500/25"
                  >
                    <Sparkles className="mr-1 h-3 w-3" />
                    Conhecer Pro
                  </Button>
                  <button
                    type="button"
                    disabled={isPending}
                    onClick={handleSkipSection}
                    className="text-[11px] text-[color:var(--ui-text-meta)] transition-colors hover:text-[color:var(--ui-text-dim)]"
                  >
                    Pular seção
                  </button>
                </>
              ) : (
                <>
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

                  {!isManual && step.next_hint && (() => {
                    const nextSection = state!.sections.find(s => s.id === step.next_hint!.section)
                    const nextRoute = nextSection?.route ?? `/${step.next_hint.section}`
                    return (
                      <Button
                        variant="ghost"
                        size="sm"
                        asChild
                        className="h-7 px-3 text-[11px] text-[color:var(--ui-accent)]"
                      >
                        <Link to={nextRoute}>
                          Ir para próxima etapa
                          <ChevronRight className="h-3 w-3" />
                        </Link>
                      </Button>
                    )
                  })()}

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
                </>
              )}
            </div>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  )
}
