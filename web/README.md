# DocOps Web

Frontend for DocOps Agent, built with React + TypeScript + Vite.

## Prerequisites
- Node `20+`
- Backend API running (default `http://127.0.0.1:8000`)

## Environment

Copy and edit:
```bash
cp .env.example .env.local
```

Default:
```env
VITE_API_URL=http://localhost:8000
```

## Development
```bash
npm ci
npm run dev
```

Default dev URL: `http://localhost:5173`

## Quality checks
```bash
npm run lint
npm run build
```

## E2E (Playwright)
```bash
npm run playwright:install
npm run test:e2e
```

Other modes:
```bash
npm run test:e2e:headed
npm run test:e2e:ui
npm run test:e2e:debug
```

## Build output
- Vite output: `web/dist`
- Root `vercel.json` uses this output for deployment.

## Deploy notes
- For Vercel, set `VITE_API_URL` in project environment variables.
- Keep API URL aligned with backend public endpoint.
