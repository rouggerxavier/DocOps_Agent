import { defineConfig, devices } from '@playwright/test'

const isCI = Boolean(process.env.CI)

const backendCommand =
  process.platform === 'win32'
    ? 'powershell -NoProfile -ExecutionPolicy Bypass -Command ". .\\.venv\\Scripts\\Activate.ps1; python -m uvicorn docops.api.app:app --host 127.0.0.1 --port 8000"'
    : 'bash -lc "source .venv/bin/activate && python -m uvicorn docops.api.app:app --host 127.0.0.1 --port 8000"'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: isCI,
  retries: isCI ? 2 : 1,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: [
    {
      command: backendCommand,
      cwd: '..',
      url: 'http://127.0.0.1:8000/api/health',
      reuseExistingServer: !isCI,
      timeout: 120_000,
    },
    {
      command: 'npm run dev -- --host localhost --port 5173 --strictPort',
      cwd: '.',
      url: 'http://localhost:5173',
      reuseExistingServer: !isCI,
      timeout: 120_000,
    },
  ],
})
