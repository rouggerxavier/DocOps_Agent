import { expect, test, type Page } from '@playwright/test'

function buildUserFixture() {
  const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  return {
    name: `Calendar ${suffix}`,
    email: `playwright-calendar-${suffix}@example.com`,
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

test('creates reminder/schedule and exposes them in dashboard + chat calendar query', async ({ page }) => {
  test.setTimeout(180_000)
  await registerAndLogin(page)

  await page.goto('/schedule')
  await page.getByPlaceholder('Título do lembrete').fill('Revisar resumo profundo')
  await page.getByRole('button', { name: /Salvar lembrete/i }).click()
  await expect(page.getByText('Lembrete salvo no calendário')).toBeVisible()
  await expect(page.getByText('Revisar resumo profundo').first()).toBeVisible()

  await page.getByPlaceholder('Atividade fixa').fill('Bloco de estudos de arvores')
  await page.getByRole('button', { name: /Adicionar bloco/i }).click()
  await expect(page.getByText('Bloco fixo adicionado ao cronograma')).toBeVisible()

  await page.goto('/')
  await expect(page.getByText('Lembretes Hoje')).toBeVisible()
  await expect(page.getByText('Revisar resumo profundo')).toBeVisible()

  await page.goto('/chat')
  const chatInput = page.getByPlaceholder(/pergunta/i)
  await chatInput.fill('Tenho compromisso hoje na agenda?')
  await chatInput.press('Enter')
  await expect(page.getByText(/calendario|compromisso|lembrete/i).first()).toBeVisible({
    timeout: 30_000,
  })
})

