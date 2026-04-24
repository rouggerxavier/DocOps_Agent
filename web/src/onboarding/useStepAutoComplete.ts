import { useEffect, useRef } from 'react'
import { useOnboarding } from './OnboardingContext'

/**
 * Fires `step_completed` with `trigger: "auto"` once when `trigger` becomes true,
 * provided the step hasn't been completed yet according to the current onboarding state.
 *
 * Guards:
 *  - Fires at most once per component mount (firedRef), even if trigger flips back/forth.
 *  - Skips if onboarding state hasn't loaded yet.
 *  - Skips if the step is already marked completed in state (idempotency belt-and-suspenders).
 *  - Skips if tour is already completed or skipped.
 */
export function useStepAutoComplete(stepId: string, trigger: boolean) {
  const { state, postEvent } = useOnboarding()
  const firedRef = useRef(false)

  useEffect(() => {
    if (!trigger || firedRef.current) return
    if (!state || state.tour.completed || state.tour.skipped) return

    const sectionId = stepId.split('.')[0]

    for (const section of state.sections) {
      const step = section.steps.find((s) => s.id === stepId)
      if (step && step.completed_at !== null) return // already done
    }

    firedRef.current = true
    void postEvent({
      event_type: 'step_completed',
      step_id: stepId,
      section_id: sectionId,
      metadata: { trigger: 'auto' },
    })
  }, [trigger, state, stepId, postEvent])
}
