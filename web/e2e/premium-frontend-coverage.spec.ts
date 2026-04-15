import { expect, test, type Page } from '@playwright/test'

function buildUserFixture() {
  const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  return {
    name: `Premium ${suffix}`,
    email: `playwright-premium-${suffix}@example.com`,
    password: 'Playwright123!',
  }
}

async function registerAndLogin(page: Page, options?: { isAdmin?: boolean }) {
  const user = buildUserFixture()
  const isAdmin = options?.isAdmin ?? true

  await page.route('**/api/auth/me', async route => {
    if (route.request().method() !== 'GET') {
      await route.fallback()
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 1,
        name: user.name,
        email: user.email,
        is_admin: isAdmin,
        created_at: '2026-04-15T12:00:00Z',
      }),
    })
  })

  await page.goto('/register')
  await page.locator('input[type="text"]').first().fill(user.name)
  await page.locator('input[type="email"]').fill(user.email)
  await page.locator('input[type="password"]').fill(user.password)
  await page.getByRole('button', { name: /Criar conta/i }).click()
  await expect(page).toHaveURL(/\/(dashboard)?$/)
}

async function mockCapabilities(page: Page, options?: { proactiveUnlocked?: boolean }) {
  const proactiveUnlocked = options?.proactiveUnlocked ?? true
  await page.route('**/api/capabilities**', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        flags: [],
        map: {
          chat_streaming_enabled: true,
          strict_grounding_enabled: true,
          premium_trust_layer_enabled: false,
          premium_artifact_templates_enabled: true,
          premium_chat_to_artifact_enabled: true,
          personalization_enabled: true,
          proactive_copilot_enabled: true,
          premium_entitlements_enabled: true,
        },
        disable_all: false,
        enable_all: true,
        entitlements_enabled: true,
        entitlement_tier: proactiveUnlocked ? 'pro' : 'free',
        entitlement_map: {
          premium_artifact_templates: true,
          premium_chat_to_artifact: true,
          premium_personalization: true,
          premium_proactive_copilot: proactiveUnlocked,
        },
        entitlement_capabilities: [],
      }),
    })
  })
}

async function mockProactiveRecommendations(page: Page) {
  await page.route('**/api/pipeline/recommendations**', async route => {
    if (route.request().method() !== 'GET') {
      await route.fallback()
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        generated_at: '2026-04-15T12:00:00Z',
        recommendation_count: 1,
        recommendations: [
          {
            id: 'rec-coverage-1',
            category: 'coverage',
            title: 'Revisar lacuna de algebra linear',
            description: 'Priorize 20 minutos de revisao guiada com foco em vetores.',
            why_this: 'A qualidade recente caiu em exercicios de transformacao linear.',
            action_label: 'Abrir revisao',
            action_to: '/chat',
            score: 0.92,
            signals: {
              category: 'coverage',
              freshness_hours: 6,
            },
          },
        ],
      }),
    })
  })
}

test('dashboard aciona eventos de recomendacao proativa via UI', async ({ page }) => {
  test.setTimeout(120_000)

  const actions: string[] = []

  await mockCapabilities(page, { proactiveUnlocked: true })
  await mockProactiveRecommendations(page)

  await page.route('**/api/pipeline/recommendations/actions**', async route => {
    if (route.request().method() !== 'POST') {
      await route.fallback()
      return
    }

    const payload = route.request().postDataJSON() as {
      recommendation_id: string
      action: string
      category?: string
    }
    actions.push(payload.action)

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        action: payload.action,
        event_type: 'premium_recommendation_action',
        recommendation_id: payload.recommendation_id,
        category: payload.category ?? 'coverage',
        effective_until: payload.action === 'snooze' ? '2026-04-16T12:00:00Z' : null,
      }),
    })
  })

  await registerAndLogin(page)
  await page.goto('/dashboard')

  await expect(page.getByText('Proximas melhores acoes')).toBeVisible()

  await page.getByRole('button', { name: 'Adiar 24h' }).first().click()
  await expect(page.getByText('Recomendacao adiada por 24h.')).toBeVisible()

  await page.getByRole('button', { name: 'Dispensar' }).first().click()
  await expect(page.getByText('Recomendacao dispensada.')).toBeVisible()

  await page.getByRole('button', { name: /Marcar recomendacao .* como util/i }).first().click()
  await expect(page.getByText('Feedback recebido. Vamos reforcar sugestoes desse perfil.')).toBeVisible()

  await expect.poll(() => actions.length).toBeGreaterThanOrEqual(3)
  expect(actions).toEqual(expect.arrayContaining(['snooze', 'dismiss', 'feedback_useful']))
})

test('chat mostra bloqueio premium de recomendacoes e atualiza acesso', async ({ page }) => {
  test.setTimeout(120_000)

  let capabilitiesHits = 0
  await page.route('**/api/capabilities**', async route => {
    capabilitiesHits += 1
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        flags: [],
        map: {
          chat_streaming_enabled: true,
          strict_grounding_enabled: true,
          premium_trust_layer_enabled: false,
          premium_artifact_templates_enabled: true,
          premium_chat_to_artifact_enabled: true,
          personalization_enabled: true,
          proactive_copilot_enabled: true,
          premium_entitlements_enabled: true,
        },
        disable_all: false,
        enable_all: true,
        entitlements_enabled: true,
        entitlement_tier: 'free',
        entitlement_map: {
          premium_artifact_templates: true,
          premium_chat_to_artifact: true,
          premium_personalization: true,
          premium_proactive_copilot: false,
        },
        entitlement_capabilities: [],
      }),
    })
  })

  await page.route('**/api/pipeline/recommendations**', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        generated_at: '2026-04-15T12:00:00Z',
        recommendation_count: 0,
        recommendations: [],
      }),
    })
  })

  await registerAndLogin(page)
  await page.goto('/chat')

  await expect(page.getByText(/Recomendacoes proativas exigem plano premium/i)).toBeVisible()

  await page.getByRole('button', { name: /Ja fiz upgrade, atualizar acesso/i }).click()

  await expect.poll(() => capabilitiesHits).toBeGreaterThan(1)
  await expect(
    page.getByText('Acesso premium atualizado. Se o upgrade ja foi aplicado, recarregamos suas capacidades.'),
  ).toBeVisible()
})

test('preferencias renderiza analytics premium com funil e qualidade', async ({ page }) => {
  test.setTimeout(120_000)

  await mockCapabilities(page, { proactiveUnlocked: true })
  const funnelWindowRequests: string[] = []
  const recommendationWindowRequests: string[] = []
  let funnelCsvExports = 0
  let recommendationCsvExports = 0

  await page.route('**/api/analytics/premium/funnel**', async route => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/export.csv')) {
      funnelCsvExports += 1
      await route.fulfill({
        status: 200,
        contentType: 'text/csv',
        body: 'scope,touchpoint\noverall,all\n',
      })
      return
    }
    funnelWindowRequests.push(url.searchParams.get('window_days') ?? '')
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        window_days: Number(url.searchParams.get('window_days') ?? 30),
        generated_at: '2026-04-15T12:00:00Z',
        totals: {
          events: 42,
          users: 18,
          touchpoints: 2,
        },
        touchpoints: [
          {
            touchpoint: 'dashboard.proactive_recommendations',
            events: 24,
            users: 10,
            stages: {
              premium_touchpoint_viewed: { events: 16, users: 9 },
              premium_upgrade_initiated: { events: 7, users: 5 },
              premium_upgrade_completed: { events: 5, users: 4 },
              premium_feature_activation: { events: 6, users: 5 },
            },
            conversion: {
              view_to_initiated: 0.56,
              initiated_to_completed: 0.8,
              view_to_completed: 0.44,
              view_to_activation: 0.55,
            },
          },
          {
            touchpoint: 'chat.proactive_starters',
            events: 18,
            users: 8,
            stages: {
              premium_touchpoint_viewed: { events: 12, users: 7 },
              premium_upgrade_initiated: { events: 4, users: 3 },
              premium_upgrade_completed: { events: 2, users: 2 },
              premium_feature_activation: { events: 3, users: 2 },
            },
            conversion: {
              view_to_initiated: 0.43,
              initiated_to_completed: 0.67,
              view_to_completed: 0.29,
              view_to_activation: 0.29,
            },
          },
        ],
      }),
    })
  })

  await page.route('**/api/analytics/premium/recommendations**', async route => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/export.csv')) {
      recommendationCsvExports += 1
      await route.fulfill({
        status: 200,
        contentType: 'text/csv',
        body: 'scope,key\noverall,all\n',
      })
      return
    }
    recommendationWindowRequests.push(url.searchParams.get('window_days') ?? '')
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        window_days: Number(url.searchParams.get('window_days') ?? 30),
        generated_at: '2026-04-15T12:00:00Z',
        totals: {
          events: 25,
          users: 11,
          recommendations: 14,
          categories: 2,
          touchpoints: 2,
        },
        actions: {
          total: 25,
          dismiss: 5,
          snooze: 4,
          mute_category: 2,
          feedback_useful: 14,
          feedback_not_useful: 6,
          feedback_useful_rate: 0.7,
        },
        categories: [
          {
            category: 'coverage',
            users: 8,
            recommendations: 9,
            actions: {
              total: 15,
              dismiss: 2,
              snooze: 3,
              mute_category: 1,
              feedback_useful: 11,
              feedback_not_useful: 3,
              feedback_useful_rate: 0.79,
            },
          },
          {
            category: 'quality',
            users: 5,
            recommendations: 5,
            actions: {
              total: 10,
              dismiss: 3,
              snooze: 1,
              mute_category: 1,
              feedback_useful: 3,
              feedback_not_useful: 3,
              feedback_useful_rate: 0.5,
            },
          },
        ],
        touchpoints: [
          {
            touchpoint: 'dashboard.proactive_recommendations',
            users: 7,
            recommendations: 8,
            actions: {
              total: 16,
              dismiss: 2,
              snooze: 4,
              mute_category: 1,
              feedback_useful: 10,
              feedback_not_useful: 4,
              feedback_useful_rate: 0.71,
            },
          },
          {
            touchpoint: 'chat.proactive_starters',
            users: 4,
            recommendations: 6,
            actions: {
              total: 9,
              dismiss: 3,
              snooze: 0,
              mute_category: 1,
              feedback_useful: 4,
              feedback_not_useful: 2,
              feedback_useful_rate: 0.67,
            },
          },
        ],
      }),
    })
  })

  await registerAndLogin(page)
  await page.goto('/settings')

  await expect(page.getByText('Conversao e Valor Premium')).toBeVisible()
  await expect(page.getByText('Top touchpoints de conversao')).toBeVisible()
  await expect(page.getByText('Qualidade por categoria')).toBeVisible()
  await expect(page.getByText('Qualidade por touchpoint')).toBeVisible()
  await expect(page.getByText('42')).toBeVisible()
  await expect(page.getByText('70.0%')).toBeVisible()
  await expect(page.getByText('Dashboard Proactive Recommendations').first()).toBeVisible()
  await expect.poll(() => funnelWindowRequests.includes('30')).toBeTruthy()
  await expect.poll(() => recommendationWindowRequests.includes('30')).toBeTruthy()

  await page.getByRole('button', { name: '7d' }).click()
  await expect.poll(() => funnelWindowRequests.includes('7')).toBeTruthy()
  await expect.poll(() => recommendationWindowRequests.includes('7')).toBeTruthy()

  await page.getByRole('button', { name: 'CSV funil' }).click()
  await page.getByRole('button', { name: 'CSV qualidade' }).click()
  await expect(page.getByText('CSV do funil exportado.')).toBeVisible()
  await expect(page.getByText('CSV de recomendacoes exportado.')).toBeVisible()
  await expect.poll(() => funnelCsvExports).toBe(1)
  await expect.poll(() => recommendationCsvExports).toBe(1)
})
