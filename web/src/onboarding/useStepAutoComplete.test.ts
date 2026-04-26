import { renderHook } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useStepAutoComplete } from './useStepAutoComplete'

const mockPostEvent = vi.fn().mockResolvedValue({})

vi.mock('./OnboardingContext', () => ({
  useOnboarding: vi.fn(),
}))

import { useOnboarding } from './OnboardingContext'

function makeState(overrides: {
  completed?: boolean
  skipped?: boolean
  stepCompleted?: boolean
} = {}) {
  return {
    schema_version: 1,
    schema_upgrade_available: false,
    last_step_seen: null,
    tour: {
      welcome_seen: true,
      started: true,
      completed: overrides.completed ?? false,
      skipped: overrides.skipped ?? false,
      progress: { completed: 0, total: 4, required_total: 4 },
    },
    sections: [
      {
        id: 'ingest',
        title: 'Ingest',
        icon: 'upload',
        route: '/ingest',
        skipped: false,
        skipped_at: null,
        steps: [
          {
            id: 'ingest.first_upload',
            title: 'Primeiro upload',
            description: '',
            premium: false,
            completion_mode: 'auto' as const,
            completed_at: overrides.stepCompleted ? '2025-01-01T00:00:00Z' : null,
            next_hint: null,
          },
        ],
      },
    ],
  }
}

describe('useStepAutoComplete', () => {
  beforeEach(() => {
    vi.mocked(useOnboarding).mockReturnValue({
      state: makeState(),
      loading: false,
      postEvent: mockPostEvent,
      isPending: false,
      activeTour: null,
      startTour: vi.fn(),
      closeTour: vi.fn(),
    })
    mockPostEvent.mockClear()
  })

  it('fires step_completed when trigger becomes true', async () => {
    const { rerender } = renderHook(
      ({ trigger }: { trigger: boolean }) =>
        useStepAutoComplete('ingest.first_upload', trigger),
      { initialProps: { trigger: false } },
    )

    expect(mockPostEvent).not.toHaveBeenCalled()

    rerender({ trigger: true })

    expect(mockPostEvent).toHaveBeenCalledOnce()
    expect(mockPostEvent).toHaveBeenCalledWith(
      expect.objectContaining({
        event_type: 'step_completed',
        step_id: 'ingest.first_upload',
        section_id: 'ingest',
        metadata: { trigger: 'auto' },
      }),
    )
  })

  it('does not fire if step is already completed', () => {
    vi.mocked(useOnboarding).mockReturnValue({
      state: makeState({ stepCompleted: true }),
      loading: false,
      postEvent: mockPostEvent,
      isPending: false,
      activeTour: null,
      startTour: vi.fn(),
      closeTour: vi.fn(),
    })

    renderHook(() => useStepAutoComplete('ingest.first_upload', true))

    expect(mockPostEvent).not.toHaveBeenCalled()
  })

  it('does not fire if tour is already completed', () => {
    vi.mocked(useOnboarding).mockReturnValue({
      state: makeState({ completed: true }),
      loading: false,
      postEvent: mockPostEvent,
      isPending: false,
      activeTour: null,
      startTour: vi.fn(),
      closeTour: vi.fn(),
    })

    renderHook(() => useStepAutoComplete('ingest.first_upload', true))

    expect(mockPostEvent).not.toHaveBeenCalled()
  })

  it('does not fire if tour is skipped', () => {
    vi.mocked(useOnboarding).mockReturnValue({
      state: makeState({ skipped: true }),
      loading: false,
      postEvent: mockPostEvent,
      isPending: false,
      activeTour: null,
      startTour: vi.fn(),
      closeTour: vi.fn(),
    })

    renderHook(() => useStepAutoComplete('ingest.first_upload', true))

    expect(mockPostEvent).not.toHaveBeenCalled()
  })

  it('fires at most once even if trigger toggles', () => {
    const { rerender } = renderHook(
      ({ trigger }: { trigger: boolean }) =>
        useStepAutoComplete('ingest.first_upload', trigger),
      { initialProps: { trigger: true } },
    )

    rerender({ trigger: false })
    rerender({ trigger: true })

    expect(mockPostEvent).toHaveBeenCalledOnce()
  })

  it('does not fire when state is not loaded', () => {
    vi.mocked(useOnboarding).mockReturnValue({
      state: undefined,
      loading: true,
      postEvent: mockPostEvent,
      isPending: false,
      activeTour: null,
      startTour: vi.fn(),
      closeTour: vi.fn(),
    })

    renderHook(() => useStepAutoComplete('ingest.first_upload', true))

    expect(mockPostEvent).not.toHaveBeenCalled()
  })
})
