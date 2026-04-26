import { useState, useEffect, useSyncExternalStore } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Check, ChevronRight, ChevronDown, ChevronUp, Sparkles, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useOnboarding } from './OnboardingContext'
import { useCapabilities, type EntitlementCapabilityKey } from '@/features/CapabilitiesProvider'
import { trackUpgradeInitiated } from '@/features/premiumAnalytics'
import type { OnboardingSectionView } from '@/api/client'

const PREMIUM_STEP_CAPABILITIES: Partial<Record<string, EntitlementCapabilityKey>> = {
  'chat.memory': 'premium_personalization',
  'artifacts.premium_templates': 'premium_artifact_templates',
}

const mobileQuery =
  typeof window !== 'undefined' ? window.matchMedia('(max-width: 639px)') : null

function subscribeMobile(cb: () => void) {
  mobileQuery?.addEventListener('change', cb)
  return () => mobileQuery?.removeEventListener('change', cb)
}

function getMobileSnapshot() {
  return mobileQuery?.matches ?? false
}

function ProgressBar({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-[color:var(--ui-surface-3)]">
      <div
        className="h-full rounded-full bg-[color:var(--ui-accent)] transition-all duration-500"
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

function SectionBlock({
  section,
  onStepClick,
  onSkipSection,
  onUpgradeIntent,
  isPending,
}: {
  section: OnboardingSectionView
  onStepClick: (stepId: string) => void
  onSkipSection: (sectionId: string) => void
  onUpgradeIntent: (stepId: string, sectionId: string) => void
  isPending: boolean
}) {
  const capabilities = useCapabilities()
  const [collapsed, setCollapsed] = useState(false)
  const completedCount = section.steps.filter((s) => s.completed_at !== null).length
  const allDone = completedCount === section.steps.length

  function isStepLocked(stepId: string): boolean {
    const capKey = PREMIUM_STEP_CAPABILITIES[stepId]
    return Boolean(capKey && capabilities.entitlementsEnabled && !capabilities.hasCapability(capKey))
  }

  return (
    <div className="rounded-xl border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-1)]">
      <button
        type="button"
        onClick={() => setCollapsed((c) => !c)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
      >
        <span className="text-base">{section.icon}</span>
        <span className="flex-1 text-sm font-semibold text-[color:var(--ui-text)]">{section.title}</span>
        <span className="text-[11px] text-[color:var(--ui-text-meta)]">
          {completedCount}/{section.steps.length}
        </span>
        <ChevronDown
          className={cn('h-3.5 w-3.5 text-[color:var(--ui-text-dim)] transition-transform', collapsed && '-rotate-90')}
        />
      </button>

      {!collapsed && (
        <div className="border-t border-[color:var(--ui-border-soft)] px-4 pb-3 pt-2 space-y-2">
          {section.steps.map((step) => {
            const done = step.completed_at !== null
            const locked = !done && step.premium && isStepLocked(step.id)
            return (
              <div
                key={step.id}
                className={cn(
                  'flex items-center gap-3 rounded-lg px-1 py-0.5',
                  locked && 'rounded-lg border border-amber-500/20 bg-amber-900/8 px-2 py-1',
                )}
              >
                <div
                  className={cn(
                    'flex h-5 w-5 shrink-0 items-center justify-center rounded-full',
                    done
                      ? 'bg-[color:var(--ui-accent)] text-[color:var(--ui-bg)]'
                      : locked
                        ? 'border border-amber-500/40 bg-amber-900/20'
                        : 'border border-[color:var(--ui-border-strong)] bg-[color:var(--ui-surface-2)]',
                  )}
                >
                  {done && <Check className="h-3 w-3" strokeWidth={3} />}
                  {locked && <Sparkles className="h-2.5 w-2.5 text-amber-300" />}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <p className={cn('text-xs font-medium', done ? 'text-[color:var(--ui-text-dim)] line-through' : 'text-[color:var(--ui-text)]')}>
                      {step.title}
                    </p>
                    {locked && (
                      <span className="shrink-0 rounded-full bg-amber-500/20 px-1 py-px text-[8px] font-bold uppercase tracking-wider text-amber-300">
                        Pro
                      </span>
                    )}
                  </div>
                </div>
                {!done && (
                  locked ? (
                    <button
                      type="button"
                      onClick={() => onUpgradeIntent(step.id, section.id)}
                      className="flex h-7 shrink-0 items-center gap-1 rounded-lg border border-amber-500/35 bg-amber-500/12 px-2 text-[11px] text-amber-200 transition-colors hover:bg-amber-500/20"
                    >
                      <Sparkles className="h-2.5 w-2.5" />
                      Pro
                    </button>
                  ) : (
                    <Button
                      variant="ghost"
                      size="sm"
                      asChild
                      className="h-7 shrink-0 px-2 text-[11px] text-[color:var(--ui-accent)]"
                      onClick={() => onStepClick(step.id)}
                    >
                      <Link to={section.route}>
                        Ir
                        <ChevronRight className="h-3 w-3" />
                      </Link>
                    </Button>
                  )
                )}
              </div>
            )
          })}

          {!allDone && !section.skipped && (
            <div className="pt-1">
              <button
                type="button"
                disabled={isPending}
                onClick={() => onSkipSection(section.id)}
                className="text-[11px] text-[color:var(--ui-text-meta)] transition-colors hover:text-[color:var(--ui-text-dim)]"
              >
                Pular seção
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function OnboardingChecklist({ className }: { className?: string }) {
  const { state, postEvent, isPending } = useOnboarding()
  const navigate = useNavigate()
  const isMobile = useSyncExternalStore(subscribeMobile, getMobileSnapshot, () => false)
  const [hidden, setHidden] = useState(false)
  const [mobileExpanded, setMobileExpanded] = useState(false)

  // Reset local hidden flag when tour is reset on the server
  useEffect(() => {
    if (state && !state.tour.completed && !state.tour.skipped) {
      setHidden(false)
    }
  }, [state?.tour.completed, state?.tour.skipped])

  if (!state || state.tour.completed || state.tour.skipped || hidden) return null

  const { progress } = state.tour

  function handleStepClick(stepId: string) {
    void postEvent({ event_type: 'step_seen', step_id: stepId })
  }

  function handleSkipSection(sectionId: string) {
    void postEvent({ event_type: 'section_skipped', section_id: sectionId })
  }

  function handleSkipAll() {
    void postEvent({ event_type: 'tour_skipped' })
  }

  function handleUpgradeIntent(stepId: string, sectionId: string) {
    void postEvent({
      event_type: 'upgrade_intent_from_onboarding',
      step_id: stepId,
      section_id: sectionId,
      metadata: { premium_cta: stepId },
    })
    trackUpgradeInitiated({ touchpoint: 'onboarding.checklist_premium_step', metadata: { step_id: stepId } })
    void navigate('/settings')
  }

  const nonSkippedSections = state.sections.filter((s) => !s.skipped)

  const pct = progress.required_total > 0
    ? Math.round((progress.completed / progress.required_total) * 100)
    : 0

  // ── Mobile collapsed pill ──────────────────────────────────────────────────
  if (isMobile && !mobileExpanded) {
    return (
      <button
        type="button"
        onClick={() => setMobileExpanded(true)}
        className={cn(
          'flex w-full items-center gap-3 rounded-xl border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-2)] px-4 py-3',
          className,
        )}
      >
        <Sparkles className="h-4 w-4 shrink-0 text-[color:var(--ui-accent)]" />
        <div className="min-w-0 flex-1 text-left">
          <p className="text-xs font-semibold text-[color:var(--ui-text)]">Primeiros passos</p>
          <div className="mt-1 flex items-center gap-2">
            <div className="h-1 flex-1 overflow-hidden rounded-full bg-[color:var(--ui-surface-3)]">
              <div
                className="h-full rounded-full bg-[color:var(--ui-accent)] transition-all duration-500"
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="shrink-0 text-[11px] font-semibold text-[color:var(--ui-accent)]">{pct}%</span>
          </div>
        </div>
        <ChevronUp className="h-4 w-4 shrink-0 text-[color:var(--ui-text-dim)]" />
      </button>
    )
  }

  // ── Full checklist (desktop + mobile expanded) ─────────────────────────────
  return (
    <div className={cn('rounded-[1.15rem] border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-2)] p-4 sm:p-5', className)}>
      <div className="mb-4 flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-[color:var(--ui-accent)]" />
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[color:var(--ui-text-meta)]">
            Primeiros passos
          </p>
        </div>
        <div className="flex items-center gap-1">
          {isMobile && (
            <button
              type="button"
              onClick={() => setMobileExpanded(false)}
              className="flex h-7 w-7 items-center justify-center text-[color:var(--ui-text-dim)] transition-colors hover:text-[color:var(--ui-text)]"
              aria-label="Recolher checklist"
            >
              <ChevronDown className="h-4 w-4" />
            </button>
          )}
          <button
            type="button"
            onClick={() => setHidden(true)}
            className="flex h-7 w-7 items-center justify-center text-[color:var(--ui-text-dim)] transition-colors hover:text-[color:var(--ui-text)]"
            aria-label="Ocultar checklist de onboarding"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="mb-3">
        <div className="mb-1.5 flex items-center justify-between">
          <p className="text-[11px] text-[color:var(--ui-text-dim)]">
            {progress.completed} de {progress.required_total} etapas concluídas
          </p>
          <p className="text-[11px] font-semibold text-[color:var(--ui-accent)]">{pct}%</p>
        </div>
        <ProgressBar value={progress.completed} max={progress.required_total} />
      </div>

      <div className="space-y-2">
        {nonSkippedSections.map((section) => (
          <SectionBlock
            key={section.id}
            section={section}
            onStepClick={handleStepClick}
            onSkipSection={handleSkipSection}
            onUpgradeIntent={handleUpgradeIntent}
            isPending={isPending}
          />
        ))}
      </div>

      <div className="mt-4 flex items-center justify-end">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={isPending}
          onClick={handleSkipAll}
          className="h-7 px-2 text-[11px] text-[color:var(--ui-text-meta)]"
        >
          Pular tudo
        </Button>
      </div>
    </div>
  )
}
