# Shadow Admin (Local)

## Requirements
- Node.js 18+
- Admin API running at `http://localhost:8099`

## Run

```bash
npm install
npm run dev
```

## Testes E2E

```bash
npm install
npx playwright install
npm run test:e2e
```

```bash
npm run test:e2e:ui
```

```bash
PW_HEADLESS=1 npm run test:e2e
```
