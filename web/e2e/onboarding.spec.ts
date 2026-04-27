import { expect, test, type Page } from '@playwright/test'

// ── Fixtures ─────────────────────────────────────────────────────────────────

function buildUserFixture() {
  const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  return {
    name: `Onboarding ${suffix}`,
    email: `onboarding-${suffix}@example.com`,
    password: 'Playwright123!',
  }
}

const MOCK_STATE_WELCOME_UNSEEN = {
  schema_version: 1,
  schema_upgrade_available: false,
  tour: {
    welcome_seen: false,
    started: false,
    completed: false,
    skipped: false,
    progress: { completed: 0, total: 14, required_total: 12 },
  },
  sections: [
    {
      id: 'ingest',
      title: 'Inserção',
      icon: '📥',
      route: '/ingest',
      skipped: false,
      skipped_at: null,
      steps: [
        {
          id: 'ingest.types_overview',
          title: '4 formas de trazer conteúdo',
          description: 'Arquivo, URL, foto ou clip.',
          premium: false,
          completion_mode: 'manual',
          completed_at: null,
          next_hint: null,
        },
        {
          id: 'ingest.first_upload',
          title: 'Insira seu primeiro documento',
          description: 'Arraste um PDF aqui.',
          premium: false,
          completion_mode: 'auto',
          completed_at: null,
          next_hint: { section: 'chat', step: 'chat.first_question' },
        },
      ],
    },
    {
      id: 'chat',
      title: 'Chat',
      icon: '💬',
      route: '/chat',
      skipped: false,
      skipped_at: null,
      steps: [
        {
          id: 'chat.memory',
          title: 'Memória ativa (premium)',
          description: 'Descubra personalização no Pro.',
          premium: true,
          completion_mode: 'manual',
          completed_at: null,
          next_hint: null,
        },
      ],
    },
  ],
  last_step_seen: null,
}

const MOCK_STATE_WELCOME_SEEN = {
  ...MOCK_STATE_WELCOME_UNSEEN,
  tour: { ...MOCK_STATE_WELCOME_UNSEEN.tour, welcome_seen: true },
}

const MOCK_STATE_TOUR_COMPLETED = {
  ...MOCK_STATE_WELCOME_SEEN,
  tour: { ...MOCK_STATE_WELCOME_SEEN.tour, completed: true },
}

const MOCK_STATE_TOUR_SKIPPED = {
  ...MOCK_STATE_WELCOME_SEEN,
  tour: { ...MOCK_STATE_WELCOME_SEEN.tour, skipped: true },
}

// ── Helpers ──────────────────────────────────────────────────────────────────

async function registerAndLogin(page: Page) {
  const user = buildUserFixture()
  await page.goto('/register')
  await page.locator('input[type="text"]').first().fill(user.name)
  await page.locator('input[type="email"]').fill(user.email)
  await page.locator('input[type="password"]').fill(user.password)
  await page.getByRole('button', { name: /Criar conta/i }).click()
  await expect(page).toHaveURL(/\/(dashboard)?$/)
  return user
}

async function mockOnboardingState(page: Page, state: object) {
  await page.route('**/api/onboarding/state', async route => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(state),
      })
    } else {
      await route.fallback()
    }
  })
}

async function mockOnboardingEvents(page: Page, responseState = MOCK_STATE_WELCOME_SEEN) {
  await page.route('**/api/onboarding/events', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ recorded: true, state: responseState }),
    })
  })
}

async function mockOnboardingReset(page: Page) {
  await page.route('**/api/onboarding/reset', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_STATE_WELCOME_UNSEEN),
    })
  })
}

// ── Tests ─────────────────────────────────────────────────────────────────────

test.describe('WelcomeModal', () => {
  test('aparece para novo usuário com welcome_seen: false', async ({ page }) => {
    await mockOnboardingState(page, MOCK_STATE_WELCOME_UNSEEN)
    await mockOnboardingEvents(page)
    await registerAndLogin(page)

    await expect(page.getByRole('dialog', { name: /Bem-vindo/i })).toBeVisible()
    await expect(page.getByText('Oi, eu sou o DocOps')).toBeVisible()
  })

  test('não aparece quando welcome_seen: true', async ({ page }) => {
    await mockOnboardingState(page, MOCK_STATE_WELCOME_SEEN)
    await registerAndLogin(page)

    await expect(page.getByRole('dialog', { name: /Bem-vindo/i })).not.toBeVisible()
  })

  test('navega pelos 3 frames com "Próximo"', async ({ page }) => {
    await mockOnboardingState(page, MOCK_STATE_WELCOME_UNSEEN)
    await mockOnboardingEvents(page)
    await registerAndLogin(page)

    await expect(page.getByText('Oi, eu sou o DocOps')).toBeVisible()

    await page.getByRole('button', { name: /Próximo/i }).click()
    await expect(page.getByText(/Como funciono em/i)).toBeVisible()

    await page.getByRole('button', { name: /Próximo/i }).click()
    await expect(page.getByText(/Vamos começar/i)).toBeVisible()

    await expect(page.getByRole('button', { name: /Quero um tour rápido/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /Explorar sozinho/i })).toBeVisible()
  })

  test('"Explorar sozinho" dispara evento welcome_shown e fecha modal', async ({ page }) => {
    await mockOnboardingState(page, MOCK_STATE_WELCOME_UNSEEN)

    const events: string[] = []
    await page.route('**/api/onboarding/events', async route => {
      const body = route.request().postDataJSON() as { event_type: string }
      events.push(body.event_type)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ recorded: true, state: MOCK_STATE_WELCOME_SEEN }),
      })
    })

    await registerAndLogin(page)

    // Advance to frame 3
    await page.getByRole('button', { name: /Próximo/i }).click()
    await page.getByRole('button', { name: /Próximo/i }).click()
    await page.getByRole('button', { name: /Explorar sozinho/i }).click()

    await expect(page.getByRole('dialog', { name: /Bem-vindo/i })).not.toBeVisible()
    expect(events).toContain('welcome_shown')
  })

  test('"Quero um tour rápido" dispara tour_started e welcome_shown', async ({ page }) => {
    await mockOnboardingState(page, MOCK_STATE_WELCOME_UNSEEN)

    const events: string[] = []
    await page.route('**/api/onboarding/events', async route => {
      const body = route.request().postDataJSON() as { event_type: string }
      events.push(body.event_type)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ recorded: true, state: MOCK_STATE_WELCOME_SEEN }),
      })
    })

    await registerAndLogin(page)
    await page.getByRole('button', { name: /Próximo/i }).click()
    await page.getByRole('button', { name: /Próximo/i }).click()
    await page.getByRole('button', { name: /Quero um tour rápido/i }).click()

    await expect(page.getByRole('dialog', { name: /Bem-vindo/i })).not.toBeVisible()
    expect(events).toContain('tour_started')
    expect(events).toContain('welcome_shown')
  })

  test('ESC fecha o modal', async ({ page }) => {
    await mockOnboardingState(page, MOCK_STATE_WELCOME_UNSEEN)
    await mockOnboardingEvents(page)
    await registerAndLogin(page)

    await expect(page.getByRole('dialog', { name: /Bem-vindo/i })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog', { name: /Bem-vindo/i })).not.toBeVisible()
  })
})

test.describe('OnboardingChecklist', () => {
  test('renderiza no Dashboard quando tour não está completo', async ({ page }) => {
    await mockOnboardingState(page, MOCK_STATE_WELCOME_SEEN)
    await mockOnboardingEvents(page)
    await registerAndLogin(page)

    await expect(page.getByText('Primeiros passos')).toBeVisible()
  })

  test('não renderiza quando tour está completo', async ({ page }) => {
    await mockOnboardingState(page, MOCK_STATE_TOUR_COMPLETED)
    await registerAndLogin(page)

    await expect(page.getByText('Primeiros passos')).not.toBeVisible()
  })

  test('não renderiza quando tour está pulado', async ({ page }) => {
    await mockOnboardingState(page, MOCK_STATE_TOUR_SKIPPED)
    await registerAndLogin(page)

    await expect(page.getByText('Primeiros passos')).not.toBeVisible()
  })

  test('"Pular tudo" dispara evento tour_skipped', async ({ page }) => {
    await mockOnboardingState(page, MOCK_STATE_WELCOME_SEEN)

    const events: string[] = []
    await page.route('**/api/onboarding/events', async route => {
      const body = route.request().postDataJSON() as { event_type: string }
      events.push(body.event_type)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ recorded: true, state: MOCK_STATE_TOUR_SKIPPED }),
      })
    })

    await registerAndLogin(page)
    await page.getByRole('button', { name: /Pular tudo/i }).click()

    expect(events).toContain('tour_skipped')
  })
})

test.describe('SectionIntro', () => {
  test('aparece na página /ingest quando há passo pendente', async ({ page }) => {
    await mockOnboardingState(page, MOCK_STATE_WELCOME_SEEN)
    await mockOnboardingEvents(page)
    await registerAndLogin(page)

    await page.goto('/ingest')
    await expect(page.getByText('4 formas de trazer conteúdo')).toBeVisible()
  })

  test('"Pular seção" dispara section_skipped', async ({ page }) => {
    await mockOnboardingState(page, MOCK_STATE_WELCOME_SEEN)

    const events: string[] = []
    await page.route('**/api/onboarding/events', async route => {
      const body = route.request().postDataJSON() as { event_type: string; section_id?: string }
      events.push(body.event_type)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ recorded: true, state: MOCK_STATE_WELCOME_SEEN }),
      })
    })

    await registerAndLogin(page)
    await page.goto('/ingest')

    await page.getByRole('button', { name: /Pular seção/i }).first().click()
    expect(events).toContain('section_skipped')
  })

  test('passo manual mostra botão "Entendi" que dispara step_completed', async ({ page }) => {
    await mockOnboardingState(page, MOCK_STATE_WELCOME_SEEN)

    const events: string[] = []
    await page.route('**/api/onboarding/events', async route => {
      const body = route.request().postDataJSON() as { event_type: string }
      events.push(body.event_type)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ recorded: true, state: MOCK_STATE_WELCOME_SEEN }),
      })
    })

    await registerAndLogin(page)
    await page.goto('/ingest')

    await page.getByRole('button', { name: /Entendi/i }).click()
    expect(events).toContain('step_completed')
  })

  test('passo premium mostra badge "Pro" e botão "Conhecer Pro"', async ({ page }) => {
    // State with chat.memory as first pending step in chat section
    const stateWithPremiumStep = {
      ...MOCK_STATE_WELCOME_SEEN,
      sections: MOCK_STATE_WELCOME_SEEN.sections,
    }
    await mockOnboardingState(page, stateWithPremiumStep)

    // Mock entitlements: entitlements enabled, no premium_personalization
    await page.route('**/api/capabilities**', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          flags: [],
          map: { onboarding_enabled: true },
          entitlements_enabled: true,
          entitlement_map: { premium_personalization: false, premium_artifact_templates: false },
          entitlement_tier: 'free',
          disable_all: false,
          enable_all: false,
        }),
      })
    })

    await mockOnboardingEvents(page)
    await registerAndLogin(page)
    await page.goto('/chat')

    await expect(page.getByText('Pro').first()).toBeVisible()
    await expect(page.getByRole('button', { name: /Conhecer Pro/i })).toBeVisible()
  })

  test('"Conhecer Pro" dispara upgrade_intent_from_onboarding e navega para /settings', async ({ page }) => {
    const stateWithPremiumStep = { ...MOCK_STATE_WELCOME_SEEN }

    await mockOnboardingState(page, stateWithPremiumStep)
    await page.route('**/api/capabilities**', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          flags: [],
          map: { onboarding_enabled: true },
          entitlements_enabled: true,
          entitlement_map: { premium_personalization: false, premium_artifact_templates: false },
          entitlement_tier: 'free',
          disable_all: false,
          enable_all: false,
        }),
      })
    })

    const events: string[] = []
    await page.route('**/api/onboarding/events', async route => {
      const body = route.request().postDataJSON() as { event_type: string }
      events.push(body.event_type)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ recorded: true, state: stateWithPremiumStep }),
      })
    })

    await registerAndLogin(page)
    await page.goto('/chat')

    await page.getByRole('button', { name: /Conhecer Pro/i }).click()

    expect(events).toContain('upgrade_intent_from_onboarding')
    await expect(page).toHaveURL(/\/settings$/)
  })
})

test.describe('Settings tutorial card', () => {
  test('card Tutorial aparece em /settings', async ({ page }) => {
    await mockOnboardingState(page, MOCK_STATE_WELCOME_SEEN)
    await mockOnboardingEvents(page)
    await registerAndLogin(page)

    await page.goto('/settings')
    await expect(page.getByRole('heading', { name: /Tutorial/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /Rever tutorial/i })).toBeVisible()
    await expect(page.getByText(/Resetar progresso completo/i)).toBeVisible()
  })

  test('"Rever tutorial" dispara tour_reset e navega para /dashboard', async ({ page }) => {
    await mockOnboardingState(page, MOCK_STATE_WELCOME_SEEN)

    const events: string[] = []
    await page.route('**/api/onboarding/events', async route => {
      const body = route.request().postDataJSON() as { event_type: string }
      events.push(body.event_type)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ recorded: true, state: MOCK_STATE_WELCOME_UNSEEN }),
      })
    })

    await registerAndLogin(page)
    await page.goto('/settings')

    await page.getByRole('button', { name: /Rever tutorial/i }).click()

    expect(events).toContain('tour_reset')
    await expect(page).toHaveURL(/\/(dashboard)?$/)
  })

  test('"Resetar progresso completo" mostra confirmação inline', async ({ page }) => {
    await mockOnboardingState(page, MOCK_STATE_WELCOME_SEEN)
    await mockOnboardingEvents(page)
    await registerAndLogin(page)

    await page.goto('/settings')

    await page.getByText(/Resetar progresso completo/i).click()
    await expect(page.getByRole('button', { name: /Confirmar reset/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /Cancelar/i })).toBeVisible()
  })

  test('"Cancelar" no reset fecha a confirmação', async ({ page }) => {
    await mockOnboardingState(page, MOCK_STATE_WELCOME_SEEN)
    await mockOnboardingEvents(page)
    await registerAndLogin(page)

    await page.goto('/settings')
    await page.getByText(/Resetar progresso completo/i).click()
    await page.getByRole('button', { name: /Cancelar/i }).click()

    await expect(page.getByRole('button', { name: /Confirmar reset/i })).not.toBeVisible()
    await expect(page.getByText(/Resetar progresso completo/i)).toBeVisible()
  })

  test('"Confirmar reset" chama POST /reset e navega para /dashboard', async ({ page }) => {
    await mockOnboardingState(page, MOCK_STATE_WELCOME_SEEN)
    await mockOnboardingEvents(page)
    await mockOnboardingReset(page)
    await registerAndLogin(page)

    await page.goto('/settings')
    await page.getByText(/Resetar progresso completo/i).click()
    await page.getByRole('button', { name: /Confirmar reset/i }).click()

    await expect(page).toHaveURL(/\/(dashboard)?$/)
  })
})
