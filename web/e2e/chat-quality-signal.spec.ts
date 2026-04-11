import { expect, test, type Page } from '@playwright/test'

function buildUserFixture() {
  const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  return {
    name: `Quality ${suffix}`,
    email: `playwright-quality-${suffix}@example.com`,
    password: 'Playwright123!',
  }
}

async function registerAndLogin(page: Page) {
  const user = buildUserFixture()
  await page.goto('/register')
  await page.locator('input[type="text"]').first().fill(user.name)
  await page.locator('input[type="email"]').fill(user.email)
  await page.locator('input[type="password"]').fill(user.password)
  await page.getByRole('button', { name: /Criar conta/i }).click()
  await expect(page).toHaveURL(/\/$/)
}

test('chat exibe sinal de confiabilidade com orientacao quando nivel baixo', async ({ page }) => {
  test.setTimeout(90_000)
  await registerAndLogin(page)

  await page.route('**/api/chat', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        answer: 'Nao encontrei evidencias suficientes para responder com seguranca.',
        sources: [],
        intent: 'qa',
        session_id: 'chat-quality-session',
        grounding: null,
        calendar_action: null,
        action_metadata: null,
        needs_confirmation: false,
        confirmation_text: null,
        suggested_reply: null,
        active_context: {
          active_doc_ids: [],
          active_doc_names: [],
        },
        quality_signal: {
          level: 'low',
          score: 0.22,
          label: 'Baixa confiabilidade',
          reasons: ['no_retrieval', 'no_inline_sources'],
          suggested_action: 'Considere ingerir mais material sobre este tema.',
          source_count: 0,
          retrieved_count: 0,
        },
      }),
    })
  })

  await page.goto('/chat')

  const chatInput = page.locator('textarea, input[type="text"]').last()
  await chatInput.fill('me traga dados do tema X')
  await chatInput.press('Enter')

  const qualityCard = page.getByTestId('chat-quality-signal')
  await expect(qualityCard).toBeVisible({ timeout: 30_000 })
  await expect(qualityCard).toContainText('Confiabilidade: Baixa confiabilidade')
  await expect(qualityCard).toContainText('Considere ingerir mais material sobre este tema.')
})
