import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { OnboardingChecklist } from './OnboardingChecklist'

const mockPostEvent = vi.fn().mockResolvedValue({})
const mockNavigate = vi.fn()

vi.mock('./OnboardingContext', () => ({ useOnboarding: vi.fn() }))
vi.mock('@/features/CapabilitiesProvider', () => ({ useCapabilities: vi.fn() }))
vi.mock('@/features/premiumAnalytics', () => ({ trackUpgradeInitiated: vi.fn() }))
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => mockNavigate }
})

import { useOnboarding } from './OnboardingContext'
import { useCapabilities } from '@/features/CapabilitiesProvider'

function makeState(overrides: { completed?: boolean; skipped?: boolean } = {}) {
  return {
    schema_version: 1,
    schema_upgrade_available: false,
    last_step_seen: null,
    tour: {
      welcome_seen: true,
      started: true,
      completed: overrides.completed ?? false,
      skipped: overrides.skipped ?? false,
      progress: { completed: 1, total: 3, required_total: 3 },
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
            title: 'Envie seu primeiro documento',
            description: 'Arraste um PDF ou cole um link.',
            premium: false,
            completion_mode: 'auto' as const,
            completed_at: '2025-01-01T00:00:00Z',
            next_hint: null,
          },
          {
            id: 'ingest.tag',
            title: 'Organize com tags',
            description: 'Tags ajudam a encontrar documentos depois.',
            premium: false,
            completion_mode: 'manual' as const,
            completed_at: null,
            next_hint: { section: 'ingest', step: 'ingest.tag', route: '/ingest' },
          },
        ],
      },
    ],
  }
}

function setup(state = makeState()) {
  vi.mocked(useOnboarding).mockReturnValue({
    state,
    loading: false,
    postEvent: mockPostEvent,
    isPending: false,
    activeTour: null,
    startTour: vi.fn(),
    closeTour: vi.fn(),
  })
  vi.mocked(useCapabilities).mockReturnValue({
    flags: {},
    entitlements: {},
    isEnabled: () => true,
    hasCapability: () => true,
    loading: false,
    disableAll: false,
    enableAll: false,
    entitlementsEnabled: false,
    entitlementTier: 'free',
    refresh: () => Promise.resolve(undefined),
  })
}

function renderChecklist() {
  return render(
    <MemoryRouter>
      <OnboardingChecklist />
    </MemoryRouter>,
  )
}

describe('OnboardingChecklist', () => {
  beforeEach(() => {
    mockPostEvent.mockClear()
    mockNavigate.mockClear()
  })

  it('renders progress and section steps', () => {
    setup()
    renderChecklist()

    expect(screen.getByText('Envie seu primeiro documento')).toBeInTheDocument()
    expect(screen.getByText('Organize com tags')).toBeInTheDocument()
  })

  it('returns null when tour is completed', () => {
    setup(makeState({ completed: true }))
    const { container } = renderChecklist()
    expect(container).toBeEmptyDOMElement()
  })

  it('returns null when tour is skipped', () => {
    setup(makeState({ skipped: true }))
    const { container } = renderChecklist()
    expect(container).toBeEmptyDOMElement()
  })

  it('fires tour_skipped when "Pular tudo" is clicked', () => {
    setup()
    renderChecklist()

    fireEvent.click(screen.getByText('Pular tudo'))

    expect(mockPostEvent).toHaveBeenCalledWith({ event_type: 'tour_skipped' })
  })

  it('hides checklist when close button is clicked', () => {
    setup()
    renderChecklist()

    fireEvent.click(screen.getByLabelText('Ocultar checklist de onboarding'))

    expect(screen.queryByText('Envie seu primeiro documento')).not.toBeInTheDocument()
  })

  it('fires step_seen when the "Ir" button of a pending step is clicked', () => {
    setup()
    renderChecklist()

    // The step_seen event fires on the "Ir" CTA button, not on the title text
    fireEvent.click(screen.getByRole('link', { name: /Ir/i }))

    expect(mockPostEvent).toHaveBeenCalledWith(
      expect.objectContaining({ event_type: 'step_seen', step_id: 'ingest.tag' }),
    )
  })
})
