import { expect, test } from '@playwright/test'

function buildUserFixture() {
  const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  return {
    name: `Playwright ${suffix}`,
    email: `playwright-${suffix}@example.com`,
    password: 'Playwright123!',
  }
}

test('redirects unauthenticated users to /login', async ({ page }) => {
  await page.goto('/')

  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByRole('button', { name: 'Entrar' })).toBeVisible()
})

test('registers a user, navigates protected pages, and logs out', async ({ page }) => {
  const user = buildUserFixture()

  await page.goto('/register')
  await expect(page).toHaveURL(/\/register$/)

  await page.locator('input[type="text"]').first().fill(user.name)
  await page.locator('input[type="email"]').fill(user.email)
  await page.locator('input[type="password"]').fill(user.password)
  await page.getByRole('button', { name: 'Criar conta' }).click()

  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()

  await page.getByRole('link', { name: 'Chat', exact: true }).click()
  await expect(page).toHaveURL(/\/chat$/)
  await expect(page.getByText('DocOps Chat')).toBeVisible()

  await page.getByRole('link', { name: 'Documentos', exact: true }).click()
  await expect(page).toHaveURL(/\/docs$/)
  await expect(page.getByRole('heading', { name: 'Documentos Indexados' })).toBeVisible()

  await page.getByRole('link', { name: 'Artefatos', exact: true }).click()
  await expect(page).toHaveURL(/\/artifacts$/)
  await expect(page.getByRole('heading', { name: 'Artefatos' })).toBeVisible()

  await page.getByRole('button', { name: 'Sair' }).click()
  await expect(page).toHaveURL(/\/login$/)

  await page.goto('/docs')
  await expect(page).toHaveURL(/\/login$/)
})
