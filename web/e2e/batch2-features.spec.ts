import { expect, test, type Page } from '@playwright/test'

function buildUserFixture() {
  const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  return {
    name: `Batch2 ${suffix}`,
    email: `playwright-batch2-${suffix}@example.com`,
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

async function ingestClipText(page: Page, title: string, text: string) {
  await page.goto('/ingest')
  await page.getByRole('button', { name: /Clip de Texto/i }).click()
  await page.getByPlaceholder(/Anotações da aula/i).fill(title)
  await page.locator('textarea').fill(text)
  const resp = page.waitForResponse(
    (r) => r.url().includes('/api/ingest/clip') && r.status() === 200,
    { timeout: 60_000 },
  )
  await page.getByRole('button', { name: /Indexar Texto/i }).click()
  await resp
}

// ── Clip de Texto ─────────────────────────────────────────────────────────────

test('ingest clip: switches to Clip tab, types text, and ingests successfully', async ({ page }) => {
  test.setTimeout(120_000)
  await registerAndLogin(page)

  await page.goto('/ingest')
  await expect(page.getByRole('heading', { name: /Ingestão de Documentos/i })).toBeVisible()

  // Switch to clip tab
  await page.getByRole('button', { name: /Clip de Texto/i }).click()
  await expect(page.getByRole('heading', { name: /Clip de Texto/i })).toBeVisible()

  // Fill title and text
  await page.getByPlaceholder(/Anotações da aula/i).fill('Teste E2E Clip')
  await page.locator('textarea').fill(
    'Este é um texto de teste para o clip de texto do DocOps Agent. ' +
    'O objetivo é verificar que a funcionalidade de ingestão de texto funciona corretamente ' +
    'quando o usuário cola um trecho longo de texto. ' +
    'Inteligência artificial e machine learning são temas importantes na computação moderna.'
  )

  // Verify character count is shown
  await expect(page.getByText(/caracteres/i)).toBeVisible()

  // Wait for the ingest API response
  const ingestRequest = page.waitForResponse(
    (response) =>
      response.url().includes('/api/ingest/clip')
      && response.request().method() === 'POST'
      && response.status() === 200,
    { timeout: 60_000 },
  )

  await page.getByRole('button', { name: /Indexar Texto/i }).click()
  await ingestRequest

  // Verify success toast or result card
  await expect(page.getByText(/chunks indexados/i).first()).toBeVisible({ timeout: 15_000 })
})

// ── Photo / OCR tab ──────────────────────────────────────────────────────────

test('ingest photo: switches to Photo tab and shows upload UI', async ({ page }) => {
  test.setTimeout(60_000)
  await registerAndLogin(page)

  await page.goto('/ingest')

  // Switch to photo tab
  await page.getByRole('button', { name: /Foto \/ OCR/i }).click()
  await expect(page.getByRole('heading', { name: /Foto \/ OCR/i })).toBeVisible()

  // Verify UI elements are present
  await expect(page.getByPlaceholder(/Página do livro/i)).toBeVisible()
  await expect(page.getByText(/Clique para selecionar uma imagem/i)).toBeVisible()
  await expect(page.getByText(/JPG, PNG, WebP, HEIC/i)).toBeVisible()

  // The submit button should be disabled since no file is selected
  const submitBtn = page.getByRole('button', { name: /Extrair e Indexar/i })
  await expect(submitBtn).toBeVisible()
  await expect(submitBtn).toBeDisabled()
})

// ── Flashcards UI ────────────────────────────────────────────────────────────

test('flashcards: shows page, empty state, opens generate dialog with doc selector', async ({ page }) => {
  test.setTimeout(120_000)
  await registerAndLogin(page)

  // Ingest a doc first
  await ingestClipText(
    page,
    'Bio Clip',
    'A fotossíntese é o processo pelo qual as plantas convertem luz solar em energia. ' +
    'A mitocôndria é a organela responsável pela respiração celular. ' +
    'O DNA carrega a informação genética dos seres vivos.'
  )

  // Navigate to flashcards
  await page.getByRole('link', { name: /Flashcards/i }).click()
  await expect(page).toHaveURL(/\/flashcards$/)
  await expect(page.getByRole('heading', { name: /Flashcards/i })).toBeVisible()

  // Should show "Gerar Deck" button
  const generateBtn = page.getByRole('button', { name: /Gerar Deck/i })
  await expect(generateBtn).toBeVisible()

  // Open generate dialog
  await generateBtn.click()
  await expect(page.getByText('Gerar Flashcards')).toBeVisible()
  await expect(page.getByText(/Documento fonte/i)).toBeVisible()
  await expect(page.getByText(/Quantidade de cards/i)).toBeVisible()

  // Verify the clipped doc appears in the selector
  await expect(page.locator('select')).toContainText('Bio Clip')

  // Slider should show default value
  await expect(page.getByText('10 cards')).toBeVisible()

  // Cancel closes the dialog
  await page.getByRole('button', { name: /Cancelar/i }).click()
  await expect(page.getByText('Gerar Flashcards')).not.toBeVisible()
})

test('flashcards: generates deck from document and enters study session', async ({ page }) => {
  test.setTimeout(240_000)
  await registerAndLogin(page)

  // Ingest a doc
  await ingestClipText(
    page,
    'FC Source',
    'A fotossíntese é o processo pelo qual as plantas convertem luz solar em energia química. ' +
    'Clorofila é o pigmento verde presente nos cloroplastos que absorve a luz. ' +
    'A mitocôndria é a organela responsável pela respiração celular aeróbica. ' +
    'O DNA é uma molécula que armazena informação genética em formato de dupla hélice. ' +
    'Charles Darwin propôs a teoria da evolução por seleção natural.'
  )

  // Navigate to flashcards and open generate dialog
  await page.getByRole('link', { name: /Flashcards/i }).click()
  await page.getByRole('button', { name: /Gerar Deck/i }).click()
  await expect(page.getByText('Gerar Flashcards')).toBeVisible()

  // Reduce to 3 cards for speed
  const slider = page.locator('input[type="range"]')
  await slider.fill('3')

  // Click generate and wait for the API response (LLM call — may be slow)
  const generateResponse = page.waitForResponse(
    (r) => r.url().includes('/api/flashcards/generate'),
    { timeout: 180_000 },
  )
  await page.getByRole('button', { name: /^Gerar$/i }).click()

  const resp = await generateResponse

  if (resp.status() === 200) {
    // Wait for toast and deck to appear
    await expect(page.getByText(/Flashcards gerados/i)).toBeVisible({ timeout: 15_000 })

    // Deck card should appear in the grid
    await expect(page.getByText(/^\d+ cards$/).first()).toBeVisible()

    // Click on the deck to start study session
    const deckCard = page.locator('[class*="cursor-pointer"][class*="rounded-xl"]').first()
    await deckCard.click()

    // Should show the flashcard with "Pergunta" label
    await expect(page.getByText(/Pergunta/i)).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText(/Clique para ver a resposta/i)).toBeVisible()

    // Flip the card
    const flashcard = page.locator('[class*="cursor-pointer"][class*="rounded-2xl"]')
    await flashcard.click()
    await expect(page.getByText(/Resposta/i)).toBeVisible()

    // Rating buttons should appear
    await expect(page.getByText('Difícil')).toBeVisible()
    await expect(page.getByText('Bom')).toBeVisible()
    await expect(page.getByText('Fácil')).toBeVisible()

    // Rate the card
    await page.getByText('Fácil').click()

    // Go back
    await page.getByText(/Voltar/i).click()
    await expect(page.getByRole('heading', { name: /Flashcards/i })).toBeVisible()
  } else {
    // LLM call failed — verify error toast appears
    await expect(page.getByText(/Erro/i).first()).toBeVisible({ timeout: 15_000 })
  }
})

// ── Plano de Estudos ─────────────────────────────────────────────────────────

test('study plan: shows form with topic, days slider, and optional doc selector', async ({ page }) => {
  test.setTimeout(60_000)
  await registerAndLogin(page)

  await page.getByRole('link', { name: /Plano de Estudos/i }).click()
  await expect(page).toHaveURL(/\/studyplan$/)
  await expect(page.getByRole('heading', { name: /Plano de Estudos/i })).toBeVisible()

  // Topic input
  const topicInput = page.getByPlaceholder(/Cálculo Integral/i)
  await expect(topicInput).toBeVisible()

  // Days slider
  await expect(page.getByText(/Prazo:/i)).toBeVisible()

  // Generate button should be disabled without topic
  const genBtn = page.getByRole('button', { name: /Gerar Plano de Estudos/i })
  await expect(genBtn).toBeDisabled()

  // Fill topic and verify button becomes enabled
  await topicInput.fill('Fundamentos de Python')
  await expect(genBtn).toBeEnabled()
})

test('study plan: generates a plan and shows result', async ({ page }) => {
  test.setTimeout(240_000)
  await registerAndLogin(page)

  await page.getByRole('link', { name: /Plano de Estudos/i }).click()
  await page.getByPlaceholder(/Cálculo Integral/i).fill('Fundamentos de Python')

  // Generate the plan
  const planResponse = page.waitForResponse(
    (r) => r.url().includes('/api/studyplan') && r.request().method() === 'POST',
    { timeout: 180_000 },
  )

  await page.getByRole('button', { name: /Gerar Plano de Estudos/i }).click()

  const resp = await planResponse

  if (resp.status() === 200) {
    await expect(page.getByText(/Plano de estudos gerado/i)).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('button', { name: /Gerar outro/i })).toBeVisible()
    await expect(page.getByText(/Baixar artefato/i)).toBeVisible()

    // Click "Gerar outro" to return to form
    await page.getByRole('button', { name: /Gerar outro/i }).click()
    await expect(page.getByPlaceholder(/Cálculo Integral/i)).toBeVisible()
  } else {
    await expect(page.getByText(/Erro/i).first()).toBeVisible({ timeout: 15_000 })
  }
})

// ── Navigation ───────────────────────────────────────────────────────────────

test('sidebar shows Flashcards and Plano de Estudos links', async ({ page }) => {
  test.setTimeout(60_000)
  await registerAndLogin(page)

  await expect(page.getByRole('link', { name: /Flashcards/i })).toBeVisible()
  await expect(page.getByRole('link', { name: /Plano de Estudos/i })).toBeVisible()

  // Navigate to flashcards
  await page.getByRole('link', { name: /Flashcards/i }).click()
  await expect(page).toHaveURL(/\/flashcards$/)

  // Navigate to study plan
  await page.getByRole('link', { name: /Plano de Estudos/i }).click()
  await expect(page).toHaveURL(/\/studyplan$/)
})

// ── Ingest tab switcher ──────────────────────────────────────────────────────

test('ingest page: all 4 tabs are visible and switchable', async ({ page }) => {
  test.setTimeout(60_000)
  await registerAndLogin(page)

  await page.goto('/ingest')

  // All tabs should be present
  await expect(page.getByRole('button', { name: /^Upload$/i })).toBeVisible()
  await expect(page.getByRole('button', { name: /^Caminho$/i })).toBeVisible()
  await expect(page.getByRole('button', { name: /Clip de Texto/i })).toBeVisible()
  await expect(page.getByRole('button', { name: /Foto \/ OCR/i })).toBeVisible()

  // Default tab is Upload
  await expect(page.getByRole('heading', { name: /Upload de Arquivos/i })).toBeVisible()

  // Switch to Caminho
  await page.getByRole('button', { name: /^Caminho$/i }).click()
  await expect(page.getByRole('heading', { name: /Caminho do Servidor/i })).toBeVisible()

  // Switch to Clip
  await page.getByRole('button', { name: /Clip de Texto/i }).click()
  await expect(page.getByRole('heading', { name: /Clip de Texto/i })).toBeVisible()

  // Switch to Photo
  await page.getByRole('button', { name: /Foto \/ OCR/i }).click()
  await expect(page.getByRole('heading', { name: /Foto \/ OCR/i })).toBeVisible()
})
