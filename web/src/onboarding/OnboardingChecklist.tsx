import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Check, ChevronRight, ChevronDown, Sparkles, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useOnboarding } from './OnboardingContext'
import type { OnboardingSectionView } from '@/api/client'

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
  isPending,
}: {
  section: OnboardingSectionView
  onStepClick: (stepId: string) => void
  onSkipSection: (sectionId: string) => void
  isPending: boolean
}) {
  const [collapsed, setCollapsed] = useState(false)
  const completedCount = section.steps.filter((s) => s.completed_at !== null).length
  const allDone = completedCount === section.steps.length

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
            return (
              <div key={step.id} className="flex items-center gap-3">
                <div
                  className={cn(
                    'flex h-5 w-5 shrink-0 items-center justify-center rounded-full',
                    done
                      ? 'bg-[color:var(--ui-accent)] text-[color:var(--ui-bg)]'
                      : 'border border-[color:var(--ui-border-strong)] bg-[color:var(--ui-surface-2)]',
                  )}
                >
                  {done && <Check className="h-3 w-3" strokeWidth={3} />}
                </div>
                <div className="min-w-0 flex-1">
                  <p className={cn('text-xs font-medium', done ? 'text-[color:var(--ui-text-dim)] line-through' : 'text-[color:var(--ui-text)]')}>
                    {step.title}
                  </p>
                  {step.premium && !done && (
                    <span className="text-[10px] font-semibold uppercase tracking-wide text-amber-300">Premium</span>
                  )}
                </div>
                {!done && (
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
  const [hidden, setHidden] = useState(false)

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

  const nonSkippedSections = state.sections.filter((s) => !s.skipped)

  return (
    <div className={cn('rounded-[1.15rem] border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-2)] p-4 sm:p-5', className)}>
      <div className="mb-4 flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-[color:var(--ui-accent)]" />
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[color:var(--ui-text-meta)]">
            Primeiros passos
          </p>
        </div>
        <button
          type="button"
          onClick={() => setHidden(true)}
          className="text-[color:var(--ui-text-dim)] transition-colors hover:text-[color:var(--ui-text)]"
          aria-label="Ocultar checklist de onboarding"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="mb-3">
        <div className="mb-1.5 flex items-center justify-between">
          <p className="text-[11px] text-[color:var(--ui-text-dim)]">
            {progress.completed} de {progress.required_total} etapas concluídas
          </p>
          <p className="text-[11px] font-semibold text-[color:var(--ui-accent)]">
            {progress.required_total > 0
              ? `${Math.round((progress.completed / progress.required_total) * 100)}%`
              : '0%'}
          </p>
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
