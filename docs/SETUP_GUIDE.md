# Lyvern: setup guide for the owner (step by step, all free)

Follow the steps in order. Total time about 45 minutes. Nothing here costs money. Never paste a private key, a webhook secret or an API key into the chat or into any file inside the git repository.

Rule reminder: Lyvern never posts or writes anything on repositories you do not own. All tests that post happen only in your own `lyvern-sandbox` repository.

---

## Step 1: open the real code in VS Code (1 minute)
1. In VS Code choose **File > Open Folder...**
2. Type or paste `C:\Users\BHUVAN\dev\pr-intel` and press **Select Folder**.
3. In the left Explorer you should now see `apps`, `packages`, `tests`, `docs`, `docker-compose.yml`. The review logic is in `packages/lyvern/src/lyvern/engine`.
(The OneDrive folder `AI PR Review Bot` only holds a snapshot copy.)

## Step 2: try reviewer mode yourself (5 minutes)
This only reads public pull requests. It cannot post anything.
1. In VS Code choose **Terminal > New Terminal** (it opens PowerShell in the project folder).
2. Run this (one line):
   `python -m uv run lyvern review https://github.com/The-PR-Agent/pr-agent/pull/4969`
3. Wait a few seconds. You will see a block that starts with `DRAFT REVIEW - NOTHING WAS POSTED`, the PR title, a proposed verdict, and the list of findings (it may say "none reported").
4. Try another one, or ask for machine-readable output:
   `python -m uv run lyvern review jaegertracing/jaeger-ui#4787 --json`
5. If you see `error: GitHub rate limit`, wait a few minutes. If you see an authentication error, run `gh auth login` once and try again.
Note: only Python files are analysed so far. TypeScript files are listed as "not analysed" until JS/TS rules are added.

## Step 3: create your sandbox repository (3 minutes)
This is the only place the bot will ever post comments during testing.
1. Open https://github.com/new
2. **Repository name:** `lyvern-sandbox`
3. Choose **Private**.
4. Tick **Add a README file**.
5. Click **Create repository**.

## Step 4: create the webhook tunnel (2 minutes, free, no account)
GitHub has to be able to reach your computer while we test. smee.io relays messages for free.
1. Open https://smee.io and click **Start a new channel**.
2. Copy the address shown (it looks like `https://smee.io/AbCdEf123`). Keep this tab; you need the address in step 6.

## Step 5: make a folder for secrets (1 minute)
1. Open PowerShell and run: `New-Item -ItemType Directory -Force C:\Users\BHUVAN\secrets`
2. This folder is outside OneDrive and outside the git repository on purpose. Private keys will be saved here.

## Step 6: register the GitHub App (15 minutes)
1. On GitHub click your **profile photo (top right) > Settings**.
2. In the left menu scroll to the bottom and click **Developer settings**.
3. Click **GitHub Apps**, then **New GitHub App**.
4. Fill the form:
   - **GitHub App name:** a unique name, for example `lyvern-bot` (the development App here was first created as `lyvern-dev-bhuvan` and renamed; the App ID stays the same after a rename). If it says the name is taken, add digits.
   - **Homepage URL:** `https://github.com/bhuvan-somisetty/lyvern`
   - **Identifying and authorizing users:** leave **Callback URL** empty. Untick **Expire user authorization tokens** if it is ticked and you are asked; otherwise leave the defaults.
   - **Webhook:** tick **Active**. For **Webhook URL** paste your smee address from step 4. For **Secret** make a random value: in PowerShell run `python -c "import secrets;print(secrets.token_hex(32))"`, copy the output into the Secret box, and also save it in a password manager or a private note. You will need it later.
   - **Repository permissions** (click the dropdown for each):
     - **Contents:** Read-only
     - **Pull requests:** Read and write
     - **Metadata:** Read-only (it is added automatically)
     - Leave everything else as "No access".
   - **Subscribe to events:** tick **Pull request**.
   - **Where can this GitHub App be installed?** choose **Only on this account**.
5. Click **Create GitHub App**.
6. On the next page write down the **App ID** (a number near the top). The App ID is not secret.
7. Scroll to **Private keys** and click **Generate a private key**. A `.pem` file downloads. Move it to `C:\Users\BHUVAN\secrets\` and rename it `lyvern-dev.pem`. Do not open it in a chat, do not upload it anywhere, do not put it in the repo or OneDrive.
8. In the left menu of the App page click **Install App**, click **Install** next to your account, choose **Only select repositories**, select **lyvern-sandbox** only, and click **Install**.

## Step 7: get a free AI key (5 minutes)
Choose ONE. All have free tiers with limits; read their terms. For now only public code is sent.
- **Google AI Studio:** open https://aistudio.google.com/apikey, sign in, click **Create API key**, copy it.
- **Groq:** open https://console.groq.com/keys, sign in, click **Create API Key**, copy it.
- **Ollama (no key, runs on your computer):** install from https://ollama.com . It uses several GB of disk and your CPU; your disk has about 12 GB free, so this is the tightest option.
Save the key in a password manager. Do not paste it in the chat.

## Step 8: Docker (only when I ask)
For the full stack tests, Docker Desktop must be running (whale icon in the system tray). Start it from the Start menu if needed.

## What to send me when you finish
Send me only these (none are secret):
1. The sandbox repository name (`lyvern-sandbox`, or what you chose).
2. The **App ID** number.
3. Which AI provider you chose (Google AI Studio, Groq or Ollama).
4. The smee channel address is NOT secret either, but you can keep it; I will ask for it when needed.
Never send: the `.pem` file contents, the webhook secret, the API key.

## What I will do next
Add JS/TS analysis rules so jaeger-ui and jam style PRs get real analysis, build the benchmark against real human review comments (read-only), then connect the GitHub App flow in `lyvern-sandbox`.

## If something goes wrong
- **"Name already taken" when creating the App:** change the name.
- **Cannot find "Developer settings":** it is at the very bottom of the left menu in Settings, below "Security log".
- **`uv` not found:** use `python -m uv ...` exactly as written above.
- **`gh` not logged in:** run `gh auth login` and follow the prompts (choose GitHub.com and HTTPS).
- **Docker not running:** start Docker Desktop and wait for the whale icon to stop animating.

---

## Addendum: running the full local system and the dashboard
1. Start Docker Desktop (database on host port 5433, Redis on 6380): `docker compose up -d db redis`, then `uv run alembic upgrade head`.
2. API: `uv run uvicorn lyvern_api.main:app --port 8010`. Worker: `uv run celery -A lyvern_worker.app worker --pool=solo`. Webhook forwarder: `npx smee-client --url <your smee url> --target http://127.0.0.1:8010/webhooks/github`. (These three together need roughly 400 MB of free memory.)
3. Optional AI review: put `LYVERN_LLM_PROVIDER=groq` in your local `.env` (keys stay in `.env`; Groq worked in tests, Gemini model names for new keys were unstable).
4. Dashboard: generate a token with `python -c "import secrets;print(secrets.token_hex(24))"`, put `LYVERN_API_TOKEN=<token>` in the repo `.env` AND in `apps/web/.env.local` (the web app reads it on the server only), set `LYVERN_API_URL=http://127.0.0.1:8010` in `apps/web/.env.local`, then `cd apps/web && pnpm dev` and open http://localhost:3000. Without a token the API answers 503 and the page shows an error instead of data.
5. Try reviewer mode on any public PR (read-only): `uv run lyvern review owner/repo#123` and add `--llm groq` for the AI layer.

### Automated approval (off by default)
`LYVERN_APPROVE_ALLOWED_REPOS=owner/name` (comma separated, exact names) is the only way the bot may APPROVE a pull request, and only when the change is small, has no findings, every file was analysed and the risk score is at most 30. Leave it empty to disable approval everywhere.

### Re-checking conflicts when the target branch changes (one extra App setting)
GitHub sends no `pull_request` event when a push to `main` makes an open pull request conflict. Lyvern handles the `push` event for that: open the App's settings page, **Permissions & events**, and under **Subscribe to events** tick **Push** (it needs no new permission), then save. After that, each push to a branch re-checks the open pull requests that target it (at most 50, drafts skipped): a pull request that now conflicts gets the conflict comment and the bot's earlier approval of it is dismissed. Without the Push subscription this feature simply never triggers; nothing else changes.

### Dashboard login and the feedback loop
Put these in `apps/web/.env.local` (git-ignored; the web app reads them on the server only): `LYVERN_DASHBOARD_PASSWORD` (the password you type on the sign-in page), `LYVERN_SESSION_SECRET` (a long random string that signs the session cookie), plus `LYVERN_API_TOKEN` and `LYVERN_API_URL` from the dashboard section above. If either login variable is missing, every page redirects to the sign-in page and sign-in refuses to work (it fails closed). After five wrong passwords in a minute, sign-in refuses attempts for the rest of that minute. Sessions last 8 hours.

Run `uv run alembic upgrade head` once to create the new `findings` and `finding_feedback` tables. From then on every review stores its findings. Open a review on the dashboard and mark each finding Real problem, False alarm or Not sure; the overview shows the measured precision (true / (true + false), with a 95% Wilson interval and a per-rule table). Not sure answers are excluded, never guessed.

### Dependency vulnerability check (optional, off by default)
Set `LYVERN_DEPENDENCY_CHECK=osv` in the worker's environment (or `.env`) to check dependencies that a pull request pins in `requirements*.txt`, `package.json` or `go.mod` against the free OSV database (api.osv.dev, no key). Only package names and versions are sent, never code. Only exact pins are checked (`name==1.2.3`, `"name": "1.2.3"`, a `go.mod` require line); a range such as `^1.2.0` is skipped because it does not say which version is installed. A package with several advisories gets one comment listing them all, at the highest severity; High and Critical findings count as blocking. If OSV cannot be reached the review is marked incomplete and cannot be approved. Try it read-only on any public PR: `uv run lyvern review owner/repo#123 --deps`.

### Dashboard accounts and roles
Run `uv run alembic upgrade head` (creates the `users` table), then create accounts on the server:
`uv run lyvern user add alice --role reviewer` (you are asked for the password twice; it needs at least 10 characters and is stored only as a scrypt hash). Other commands: `lyvern user list`, `set-password`, `set-role`, `disable`, `enable`. Roles: `viewer` reads, `reviewer` also marks findings, `admin` the same plus the owner login. On the sign-in page type the username and password. The single owner password in `apps/web/.env.local` still works for the username `owner` (an admin), as a break-glass login. The web server re-checks the role on every verdict, and each verdict records who gave it. The login endpoint slows down repeated failures per username (8 in 5 minutes) and answers identically for a wrong user and a wrong password.

### Cross-file check
On by default. For each top-level function, class or export that a pull request deletes and does not define again, the bot reads up to 60 other files of the same language at the head commit and reports real imports or calls that would now fail. Methods are never checked (a name like `run` belongs to many classes), and names of fewer than 5 characters or common words are skipped. Turn it off with `LYVERN_CROSS_FILE_CHECK=false`, or per run with `lyvern review ... --no-xref`. If the repository files cannot be read, the review is marked incomplete and cannot be approved.

### Run the whole product with Docker (one command)
`docker compose up -d --build` starts PostgreSQL (with pgvector), Redis, the migrations, the API, the worker and the dashboard. Put these in a `.env` file next to `docker-compose.yml` (or in your shell): `LYVERN_API_TOKEN`, `LYVERN_SESSION_SECRET`, `LYVERN_DASHBOARD_PASSWORD`, and for real reviews `LYVERN_GITHUB_APP_ID`, `LYVERN_GITHUB_WEBHOOK_SECRET` and `LYVERN_GITHUB_APP_PRIVATE_KEY_HOST_PATH` (the path of the App's `.pem` file on your computer; it is mounted read-only into the containers and never copied into an image). Dashboard: http://localhost:3000 (change with `LYVERN_WEB_PORT`); API: port 8000 (change with `LYVERN_API_PORT`, for example when something else already uses 8000). Without the token or secret the dashboard stays locked instead of opening. Check it with `docker compose ps`. The images are rebuilt with `docker compose build`; run it after pulling new code, because the database migrations ship inside the image.

### Public demo on Vercel
`apps/web` can run in demo mode (`LYVERN_DEMO=1`): it then shows built-in SAMPLE data (invented repositories, pull requests and findings, defined in `src/lib/demo.ts`), needs no API, database or login, and cannot save verdicts. It is live at https://lyvern.vercel.app. The real data never reaches it, because the hosted site has no connection to your database. To redeploy after changing the dashboard: `cd apps/web` then `vercel deploy --prod` (the project is linked as `lyvern`; `LYVERN_DEMO=1` is stored in the project's Production and Preview environment variables; the upload excludes `.env*` through `.vercelignore`). Hosting the REAL product (API, Postgres, Redis and a worker that stays running) is a separate step; free tiers for an always-on worker are limited, so it is not done.

### Optional noisy style rules
`LYVERN_STRICT_STYLE_RULES=true` (or `lyvern review ... --strict-style`) also runs rules that were right too rarely on real code to be on by default. Today that is the JavaScript/TypeScript empty-catch rule: a real problem in 8 of 56 labelled cases (14%), because deliberate best-effort catches are common.
