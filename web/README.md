# FORGE Web

Next.js 16 (App Router, Cache Components, Partial Prefetching), TypeScript,
Tailwind CSS v4, Lucide icons, Geist Sans/Mono.

## Run

```bash
npm install
cp .env.example .env.local     # FORGE_API_URL → the FastAPI service
npm run dev
```

Scripts: `lint`, `typecheck`, `build`. Requires the API and database to be
running (see `api/README.md`).

## How data flows

- Server Components fetch from the API via `src/lib/api.ts`; mutations go
  through Server Actions in `src/app/actions.ts`. The browser never calls the
  API directly, and `FORGE_API_URL` is not exposed to client bundles.
- The anonymous learner id lives in an httpOnly `forge_learner` cookie,
  created on the first "Start assessment". Progress is stored server-side, so
  it survives refreshes and restarts (but not clearing cookies).
- `/assessments/[id]` asks the API for the current question on every render.
  The API returns the same question until it's answered, so a refresh resumes
  in place. After submitting, "Next question" refreshes server data.

## Routes

| Route | Purpose |
| --- | --- |
| `/` | Dashboard: resume card, skills, recent sessions |
| `/tracks` | All skills |
| `/tracks/[slug]` | Topics, difficulty picker, start assessment |
| `/assessments/[id]` | Answer → submit → feedback → next; summary when complete |
| `/assessments/[id]/items/[itemId]` | Review a submitted answer's feedback |
| `/progress` | Per-skill counts and answer history |
