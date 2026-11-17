# Actions mode: run Lyvern for free, with no server

The normal setup (API, worker, Redis, PostgreSQL, a tunnel) runs on your own machine. **Actions mode** removes all of that: the review runs on a free GitHub-hosted runner every time a pull request is opened or updated. Nothing to host, nothing to keep running, no cost for public repositories (private repositories use the free Actions minutes of your plan).

## How it works
1. A pull request is opened or pushed to.
2. `.github/workflows/lyvern-review.yml` starts a runner with a throw-away PostgreSQL service.
3. The runner installs Lyvern, then runs `lyvern action --event $GITHUB_EVENT_PATH`.
4. `lyvern action` rebuilds the bot's own earlier reviews on that pull request from GitHub (so a stale "changes requested" or approval can still be dismissed), then runs the same review job as the server version and posts through the GitHub App.
5. The runner is thrown away.

The workflow uses `pull_request_target` and checks out Lyvern, never the pull request. **No code from the pull request is executed**; Lyvern reads the diff through the GitHub API. That is what makes it safe to give the job the App key.

## Set it up (about 5 minutes)
1. Install the Lyvern GitHub App on the repository (already done for your own repositories).
2. In the repository: Settings, Secrets and variables, Actions. Add secrets:
   - `LYVERN_APP_ID`: the App id.
   - `LYVERN_APP_PRIVATE_KEY`: the full contents of the App's `.pem` file.
   - `LYVERN_GROQ_API_KEY` (optional): turns on the AI layer.
3. Optional variable `LYVERN_APPROVE_ALLOWED_REPOS`: set to `owner/repo` to let the bot approve clean pull requests there. Left empty, it never approves.
4. Copy `.github/workflows/lyvern-review.yml` into the repository.

## Limits (honest)
- It reviews on pull request events only. The "base branch moved, re-check conflicts" feature of the server version needs a push listener and is not part of Actions mode; a conflict is still detected whenever the pull request is updated.
- Each run installs Lyvern (about a minute). Reviews arrive within a few minutes, not seconds.
- The dashboard needs the database, so runs from Actions mode are not recorded on it.
- The workflow pulls Lyvern from the `develop` branch. For stricter supply-chain safety, pin `ref:` to a commit.
