# Owner checklist: the steps only the repository owner can do

Everything here needs your GitHub account, your screen or your decision. Each step says where to
click and how to know it worked. Do them in this order.

## 1. Turn on the Push event (enables the base-branch conflict re-check)
1. Open https://github.com/settings/apps/lyvern-bot
2. In the left menu click **Permissions & events**.
3. Scroll to **Subscribe to events** and tick **Push**. (If the box is greyed out, set
   **Contents** to *Read-only* under Repository permissions first; the App already has it.)
4. Click **Save changes** at the bottom.
5. Check: push any commit to `main` of `lyvern-sandbox`; open sandbox pull requests that now
   conflict get the conflict comment within a minute (the API and worker must be running).

## 2. Sign in to the dashboard
1. Open `apps/web/.env.local` in the repo. It has `LYVERN_DASHBOARD_PASSWORD` (your password),
   `LYVERN_SESSION_SECRET`, `LYVERN_API_TOKEN` and `LYVERN_API_URL`. You may change the password
   to one you prefer; keep it long.
2. Start the three parts (each in its own terminal, from the repo folder):
   - `docker compose up -d db redis`
   - `uv run uvicorn lyvern_api.main:app --port 8010`
   - `uv run celery -A lyvern_worker.app worker --pool=solo`
   - `cd apps/web` then `pnpm dev`
3. Open http://localhost:3000, type the password, press **Sign in**. After five wrong tries in a
   minute it refuses for the rest of that minute.

## 3. Label findings (this is what turns "precision unknown" into a measured number)
1. Open a pull request in `lyvern-sandbox` (or use the existing ones) so the bot reviews it.
2. On the dashboard click the review, then for every finding press **Real problem**,
   **False alarm** or **Not sure**. Be honest: a false alarm is useful information.
3. Go back to the overview: **Measured precision** appears once at least one finding is
   marked real or false, with a 95% interval. A handful of labels gives a very wide interval;
   say so when you quote it. Aim for 30 or more labels before using the number on a resume.

## 4. Optional switches (environment variables for the worker, in `.env`)
- `LYVERN_APPROVE_ALLOWED_REPOS=owner/name` lets the bot approve in that repository only
  (zero findings and no conflicts required). Leave empty to disable approval everywhere.
- `LYVERN_DEPENDENCY_CHECK=osv` turns on the known-vulnerability check for pinned dependencies.
- `LYVERN_LLM_PROVIDER=groq` turns on AI observations (never blocking).
- `LYVERN_ATTENTION_MODEL=false` hides the advisory statistical estimate (on by default).

## 5. Things that need a decision from you
- **Trademark and domain** for "Lyvern": search the name at your trademark office and at a
  domain registrar before you publish it widely (you asked to leave this one out for now).
- **GitHub App logo and name** are already set (`lyvern-bot`). To change the logo, upload a file
  from `assets/brand/` at https://github.com/settings/apps/lyvern-bot under *Display information*.

## 6. Housekeeping on your machine
- **Docker data now lives on the D: drive** (`D:\docker-data\disk`), reached through a folder
  junction at `%LOCALAPPDATA%\Docker\wsl\disk`. Do not delete `D:\docker-data`; it holds your
  databases for every project. The uv cache is on `D:\dev-cache\uv` (`UV_CACHE_DIR`).
- Git signs commits with your GPG key. If a passphrase window appears, type your passphrase; the
  commit finishes when you do.
