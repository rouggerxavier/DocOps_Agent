import { expect, test, type Page } from '@playwright/test'
import { fileURLToPath } from 'node:url'

const uploadFixturePath = fileURLToPath(new URL('../../docs/e2e-upload.txt', import.meta.url))

function buildUserFixture() {
  const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  return {
    name: `Playwright ${suffix}`,
    email: `playwright-fullflow-${suffix}@example.com`,
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

async function uploadFixtureDocument(page: Page) {
  const ingestRequest = page.waitForResponse(
    (response) =>
      response.url().includes('/api/ingest')
      && response.request().method() === 'POST'
      && response.status() === 200,
    { timeout: 90_000 },
  )

  await page.goto('/ingest')
  await page.setInputFiles('input[type="file"]', uploadFixturePath)
  await page.getByRole('button', { name: /Indexar Arquivos/i }).click()
  await ingestRequest
}

async function createStudyPlanArtifact(page: Page, topic: string) {
  await page.goto('/artifacts')
  await page.getByRole('button', { name: /Novo Artefato/i }).click()
  await page.getByRole('textbox', { name: 'Ex: Python para iniciantes' }).fill(topic)
  await page.getByRole('button', { name: /^Gerar$/i }).click()
  await expect(page.getByRole('button', { name: /^Fechar$/i })).toBeVisible({ timeout: 120_000 })
}

async function closeActiveModal(page: Page) {
  const modal = page.locator('div.fixed.inset-0').last()
  await expect(modal).toBeVisible({ timeout: 15_000 })
  await modal.getByRole('button').first().click()
  await expect(modal).toBeHidden({ timeout: 15_000 })
}

test('full flow: upload, brief/deep summary, chat, and study-plan artifact', async ({ page }) => {
  test.setTimeout(240_000)

  await registerAndLogin(page)
  await uploadFixtureDocument(page)

  // In app runtime, docs list may stay stale right after ingest due query cache.
  // A hard navigation ensures we fetch the latest server state.
  await page.goto('/docs')
  await expect(page.getByText('e2e-upload.txt', { exact: true }).first()).toBeVisible({
    timeout: 60_000,
  })

  await page.getByRole('button', { name: 'Resumir' }).click()
  await page.getByRole('button', { name: /Gerar Resumo Breve/i }).click()
  await expect(page.getByRole('button', { name: /Gerar outro/i })).toBeVisible({ timeout: 120_000 })
  await closeActiveModal(page)

  await page.getByRole('button', { name: 'Resumir' }).click()
  await page.getByRole('button', { name: /Resumo Aprofundado/i }).first().click()
  await page.getByRole('button', { name: /Gerar Resumo Aprofundado/i }).click()
  await expect(page.getByRole('button', { name: /Gerar outro/i })).toBeVisible({ timeout: 180_000 })
  await expect(page.getByText('Agent error')).not.toBeVisible()
  await closeActiveModal(page)

  await page.getByRole('link', { name: /^Chat$/, exact: true }).click()
  const chatInput = page.getByPlaceholder(/pergunta/i)
  await chatInput.fill('Resuma e2e-upload.txt em topicos principais.')
  await chatInput.press('Enter')
  await expect(page.getByRole('button', { name: /fonte\(s\) citada\(s\)/i })).toBeVisible({
    timeout: 120_000,
  })

  await createStudyPlanArtifact(page, 'Plano de estudos de Python para ciencia de dados')
  await page.getByRole('button', { name: /^Fechar$/i }).click()
  await expect(page.getByText(/Plano de estudos de Python para ciencia de dados/i).first()).toBeVisible()
})

test('artifact preview uses authenticated request and renders content', async ({ page }) => {
  test.setTimeout(180_000)

  await registerAndLogin(page)
  await createStudyPlanArtifact(page, 'Plano de estudos rapido de Python')
  await page.getByRole('button', { name: /^Fechar$/i }).click()

  await page.getByRole('button', { name: 'Preview' }).first().click()
  await expect(page.getByText('Not authenticated')).not.toBeVisible()
  await expect(page.getByText(/Fonte/i).first()).toBeVisible({ timeout: 30_000 })
})
