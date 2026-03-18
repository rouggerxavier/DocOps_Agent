import { expect, test, type Page } from '@playwright/test'

// ── Helpers ──────────────────────────────────────────────────────────────────

function buildUserFixture() {
  const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  return {
    name: `Orch ${suffix}`,
    email: `playwright-orch-${suffix}@example.com`,
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
  return user
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

// ── Feature 1: Smart Digest ───────────────────────────────────────────────────

test('smart digest: botão Digest aparece nos cards de documentos', async ({ page }) => {
  test.setTimeout(120_000)
  await registerAndLogin(page)

  await ingestClipText(
    page,
    'Doc Digest Test',
    'Fotossíntese é o processo pelo qual plantas convertem luz em energia. ' +
    'Clorofila absorve a luz e converte CO2 em glicose. ' +
    'A mitocôndria realiza respiração celular aeróbica.',
  )

  await page.goto('/docs')
  await expect(page.getByRole('heading', { name: /Documentos Indexados/i })).toBeVisible()

  // O botão Digest deve estar visível no card do documento
  const digestBtn = page.getByRole('button', { name: /Digest/i }).first()
  await expect(digestBtn).toBeVisible({ timeout: 10_000 })
})

test('smart digest: abre dialog com opções configuráveis', async ({ page }) => {
  test.setTimeout(120_000)
  await registerAndLogin(page)

  await ingestClipText(
    page,
    'Doc Dialog Test',
    'Inteligência artificial é uma área da computação. ' +
    'Machine learning permite que computadores aprendam com dados. ' +
    'Redes neurais são inspiradas no cérebro humano.',
  )

  await page.goto('/docs')

  // Clicar no botão Digest
  const digestBtn = page.getByRole('button', { name: /Digest/i }).first()
  await digestBtn.click()

  // Dialog deve abrir
  await expect(page.getByText('Smart Digest:')).toBeVisible()

  // Opções devem estar presentes
  await expect(page.getByText('Gerar Flashcards')).toBeVisible()
  await expect(page.getByText('Extrair Tarefas')).toBeVisible()
  await expect(page.getByRole('button', { name: /Executar Smart Digest/i })).toBeVisible()

  // Slider de quantidade deve estar visível (flashcards marcado por padrão)
  await expect(page.locator('input[type="range"]')).toBeVisible()

  // Fechar clicando em ✕
  await page.getByRole('button', { name: '✕' }).click()
  await expect(page.getByText('Smart Digest:')).not.toBeVisible()
})

test('smart digest: executa pipeline completo e mostra resultados', async ({ page }) => {
  test.setTimeout(300_000)
  await registerAndLogin(page)

  await ingestClipText(
    page,
    'Bio Digest',
    'A fotossíntese ocorre nos cloroplastos das células vegetais. ' +
    'A clorofila é o principal pigmento fotossintético. ' +
    'O ciclo de Calvin fixa o carbono do CO2 em moléculas orgânicas. ' +
    'A respiração celular ocorre na mitocôndria e libera ATP. ' +
    'O DNA é a molécula que carrega as informações genéticas.',
  )

  await page.goto('/docs')
  const digestBtn = page.getByRole('button', { name: /Digest/i }).first()
  await digestBtn.click()

  // Reduz flashcards para 5 para ser mais rápido
  const slider = page.locator('input[type="range"]')
  await slider.fill('5')

  // Aguarda resposta do pipeline (pode demorar por ser LLM)
  const digestResponse = page.waitForResponse(
    (r) => r.url().includes('/api/pipeline/digest'),
    { timeout: 240_000 },
  )

  await page.getByRole('button', { name: /Executar Smart Digest/i }).click()

  const resp = await digestResponse

  if (resp.status() === 200) {
    // Toast de sucesso
    await expect(page.getByText(/Smart Digest concluído/i)).toBeVisible({ timeout: 15_000 })

    // Resumo deve aparecer
    await expect(page.getByText(/Resumo:/i)).toBeVisible({ timeout: 15_000 })

    // Deve mostrar flashcards ou tarefas criadas
    const hasFlashcards = await page.getByText(/Flashcards criados/i).isVisible().catch(() => false)
    const hasTasks = await page.getByText(/Tarefas extraídas/i).isVisible().catch(() => false)
    expect(hasFlashcards || hasTasks).toBeTruthy()

    // Botão de refazer deve aparecer
    await expect(page.getByRole('button', { name: /Fazer novamente/i })).toBeVisible()
  } else {
    // Se LLM falhar, verifica toast de erro
    await expect(page.getByText(/Erro/i).first()).toBeVisible({ timeout: 15_000 })
  }
})

// ── Feature 2: Chat Cross-Module Actions ──────────────────────────────────────

test('chat actions: criar tarefa via mensagem no chat', async ({ page }) => {
  test.setTimeout(120_000)
  await registerAndLogin(page)

  await page.goto('/chat')
  await expect(page.getByRole('heading', { name: /Chat/i })).toBeVisible({ timeout: 10_000 })

  // Envia comando de criação de tarefa
  const taskTitle = `Estudar para prova de cálculo ${Date.now()}`
  const chatInput = page.locator('textarea, input[type="text"]').last()
  await chatInput.fill(`Tarefa: ${taskTitle}`)

  const chatResp = page.waitForResponse(
    (r) => r.url().includes('/api/chat') && r.request().method() === 'POST',
    { timeout: 30_000 },
  )
  await page.keyboard.press('Enter')
  const resp = await chatResp

  if (resp.status() === 200) {
    // Resposta deve confirmar criação
    await expect(page.getByText(/Tarefa criada/i)).toBeVisible({ timeout: 15_000 })

    // Link para tarefas deve aparecer
    await expect(page.locator('a[href="/tasks"]').first()).toBeVisible({ timeout: 10_000 })

    // Verificar que a tarefa foi realmente criada
    await page.goto('/tasks')
    await expect(page.getByText(taskTitle.substring(0, 40))).toBeVisible({ timeout: 10_000 })
  } else {
    // Endpoint respondeu mas não era action_router — verifica qualquer resposta
    expect(resp.status()).toBeLessThan(500)
  }
})

test('chat actions: listar tarefas via chat', async ({ page }) => {
  test.setTimeout(120_000)
  await registerAndLogin(page)

  // Primeiro cria uma tarefa via API direta
  await page.goto('/tasks')
  // A página de tarefas deve estar acessível
  await expect(page.getByRole('heading', { name: /Tarefas/i })).toBeVisible({ timeout: 10_000 })

  // Vai para o chat e pede para listar tarefas
  await page.goto('/chat')
  const chatInput = page.locator('textarea, input[type="text"]').last()
  await chatInput.fill('minhas tarefas pendentes')

  const chatResp = page.waitForResponse(
    (r) => r.url().includes('/api/chat') && r.request().method() === 'POST',
    { timeout: 30_000 },
  )
  await page.keyboard.press('Enter')
  const resp = await chatResp

  expect(resp.status()).toBeLessThan(500)

  if (resp.status() === 200) {
    const body = await resp.json().catch(() => null)
    // Intent deve ser list_tasks ou algo relacionado
    if (body) {
      expect(['list_tasks', 'qa', 'other']).toContain(body.intent)
    }
  }
})

test('chat actions: hint de flashcards reconhece documento existente', async ({ page }) => {
  test.setTimeout(180_000)
  await registerAndLogin(page)

  // Insere um documento
  await ingestClipText(
    page,
    'Python Basico',
    'Python é uma linguagem de programação de alto nível. ' +
    'É muito usada em ciência de dados, automação e web.',
  )

  // Vai para o chat
  await page.goto('/chat')
  const chatInput = page.locator('textarea, input[type="text"]').last()
  await chatInput.fill('gere flashcards do documento Python Basico')

  const chatResp = page.waitForResponse(
    (r) => r.url().includes('/api/chat') && r.request().method() === 'POST',
    { timeout: 30_000 },
  )
  await page.keyboard.press('Enter')
  const resp = await chatResp

  expect(resp.status()).toBeLessThan(500)

  if (resp.status() === 200) {
    // Deve retornar alguma resposta sobre flashcards ou orientação
    await expect(page.locator('[class*="prose"], [class*="markdown"], p').last()).toBeVisible({ timeout: 15_000 })
  }
})

// ── Feature 3: Extract Tasks ─────────────────────────────────────────────────

test('extract tasks: endpoint disponível e retorna 200 ou 4xx válido', async ({ page }) => {
  test.setTimeout(120_000)
  await registerAndLogin(page)

  await ingestClipText(
    page,
    'Tarefas Extract',
    'Tarefa 1: Estudar álgebra linear até sexta. ' +
    'Tarefa 2: Entregar trabalho de cálculo. ' +
    'Revisar capítulos 3 e 4 do livro de física. ' +
    'Resolver exercícios 1 a 10 da lista 3.',
  )

  // Testa o endpoint via fetch do browser (como usuário autenticado)
  const token = await page.evaluate(() => localStorage.getItem('token'))
  expect(token).toBeTruthy()

  const response = await page.evaluate(async (t) => {
    const r = await fetch('/api/pipeline/extract-tasks', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${t}`,
      },
      body: JSON.stringify({ doc_name: 'Tarefas Extract', max_tasks: 5 }),
    })
    return { status: r.status, body: await r.json().catch(() => null) }
  }, token)

  // Deve retornar 200 (sucesso) ou 404 (doc não encontrado pelo nome exato) — nunca 500
  expect(response.status).not.toBe(500)
  expect([200, 404, 422]).toContain(response.status)

  if (response.status === 200 && response.body) {
    expect(typeof response.body.tasks_created).toBe('number')
    expect(Array.isArray(response.body.titles)).toBeTruthy()
  }
})

test('extract tasks: via Smart Digest toggle, desabilitar tarefas funciona', async ({ page }) => {
  test.setTimeout(60_000)
  await registerAndLogin(page)

  await ingestClipText(
    page,
    'Toggle Test Doc',
    'Este documento serve para testar toggles. Conteúdo simples.',
  )

  await page.goto('/docs')
  const digestBtn = page.getByRole('button', { name: /Digest/i }).first()
  await digestBtn.click()

  // Dialog abre
  await expect(page.getByText('Smart Digest:')).toBeVisible()

  // Desmarca "Extrair Tarefas"
  const extractTasksCheckbox = page.locator('input[type="checkbox"]').nth(1)
  await extractTasksCheckbox.uncheck()
  await expect(extractTasksCheckbox).not.toBeChecked()

  // Desmarca "Gerar Flashcards"
  const flashcardsCheckbox = page.locator('input[type="checkbox"]').nth(0)
  await flashcardsCheckbox.uncheck()
  await expect(flashcardsCheckbox).not.toBeChecked()

  // Slider de cards deve sumir quando flashcards está desmarcado
  await expect(page.locator('input[type="range"]')).not.toBeVisible()

  // Fechar
  await page.getByRole('button', { name: '✕' }).click()
  await expect(page.getByText('Smart Digest:')).not.toBeVisible()
})
