# Security Audit: matneco.com

- **Date:** 2026-10-24
- **Scope:** Full git history of every branch (11 commits on `main` and `origin/claude/shared-ember-sandbox-docker-4vbaph`), plus every dependency declaration ever committed.
- **Mode:** Report only. This PR adds this file and changes no code.
- **Redaction:** This report gives no secret values, usernames or passwords. Each finding names only the file, the commits and the type.

## Method

| Check | Tool / approach | Result |
|---|---|---|
| Committed secrets, full history | `gitleaks` v8.21.2, `git --log-opts=--all`, `--redact` | 0 findings |
| Committed secrets, manual follow-up | Searched every added line in `git log --all -p` for password / token / key / secret patterns, then read each hit | **1 critical finding that gitleaks missed** (see F-1) |
| Python dependencies | Looked for `requirements*.txt`, `pyproject.toml`, `Pipfile`, `setup.py` in every commit | None. `seed.py` uses only the standard library, so `pip-audit` has nothing to scan |
| JS dependencies | Looked for `package.json` and lockfiles in every commit | None. `npm audit` has nothing to scan |
| Container / runtime dependencies | Reviewed `Dockerfile` and `docker-compose.yml` (sandbox branch) | Unpinned versions (see F-3) |
| Third-party assets in pages | Reviewed `<script>` / `<link>` tags in all HTML | Google Fonts only, and no third-party scripts |

## Findings (most severe first)

| ID | Severity | Title | Where |
|---|---|---|---|
| F-1 | **Critical** | Hardcoded login credentials in a public repo's history | `login.html`, commits `b113cbb` to `1566bf1` |
| F-2 | Medium | Sandbox exposes Stash on all interfaces and prints its API key to logs | branch `claude/shared-ember-sandbox-docker-4vbaph` |
| F-3 | Medium | Unpinned container images and packages | same branch: `docker-compose.yml`, `seed/Dockerfile` |
| F-4 | Low | No Content-Security-Policy, and Google Fonts loaded from a third party | `index.html` |
| F-5 | Info | Commit metadata exposes a personal machine hostname | commit `6de4448` and others |
| F-6 | Info | Stale feature branch is publicly visible | `claude/shared-ember-sandbox-docker-4vbaph` |

---

### F-1: Hardcoded login credentials in history (Critical)

- **Type:** Plaintext username/password table (client-side auth).
- **File:** `login.html` (a `USERS` object, around lines 186 to 207 in the first commit).
- **Commits containing it:** `b113cbb` (introduced), `98bb2b9`, `04873b1`, `6f5ca2c`, `1566bf1`.
- **Removed in:** `6de4448` ("Simplify login - direct to plus.matneco.com"). It is **not** in the current `main` tree, but it **remains in history**.
- **Scale:** 20 distinct accounts, each with a unique 10-character password.
- **Why critical:** The repository is **public**, so anyone can read these credentials with `git log -p`. Forks, clones and third-party mirrors may already hold copies. The login was also client-side, so it never protected anything: the check and the destination were both in the page source.
- **Why gitleaks missed it:** The default ruleset matches known token formats and high-entropy strings. Short human-style passwords in a JS object fall below its thresholds. That is a good reason to run a manual review alongside the tool.

**Suggested fix:**
1. **Rotate first.** Treat all 20 passwords as compromised. If any of them was reused on `plus.matneco.com`, a media server, email, or anywhere else, change it there now and tell the affected users. Rewriting history does not undo the exposure.
2. Purge the history: run `git filter-repo --path login.html --invert-paths` (or `--replace-text`) on a fresh mirror clone, then force-push all branches and tags. Ask GitHub Support to purge cached views and dangling commits. Anyone with an existing clone will need to re-clone.
3. Prevent a repeat: never put auth in a static site. Keep login on the real backend (as `plus.matneco.com` now does). Add a `gitleaks` pre-commit hook or GitHub Action with a custom rule for `password\s*[:=]` inside JS objects, and turn on GitHub secret scanning and push protection for the repo.

### F-2: Sandbox network exposure and API key in logs (Medium)

- **Type:** Insecure default configuration.
- **Files:** `ember-sandbox/docker-compose.yml`, `ember-sandbox/seed/seed.py` (commit `8b0fa39`, branch only).
- **Details:**
  - The port mapping `"${STASH_PORT:-9999}:9999"` binds to `0.0.0.0`, so the server is reachable from the whole LAN, or the internet if the host is exposed. The optional `tunnel` profile publishes it on the internet on purpose.
  - `seed.py` prints the generated Stash API key to stdout, so it persists in `docker compose logs`, and in any log shipping, until the container is removed.
  - If `STASH_PASSWORD` were ever empty, `seed.py` leaves Stash with **no login**. Compose's `${STASH_PASSWORD:?…}` prevents that today, but the script still falls back to open access when run on its own.
- **Committed secrets:** None. `.env` is git-ignored, and `.env.example` holds only a placeholder password and an empty tunnel token.

**Suggested fix:** Bind to loopback by default (`"127.0.0.1:${STASH_PORT:-9999}:9999"`) and make LAN exposure opt-in. Write the API key to `volumes/out/` with `0600` permissions and print only its path. Make `seed.py` exit with an error if no password is set. When using the tunnel, put Cloudflare Access in front of it.

### F-3: Unpinned container images and packages (Medium)

- **Type:** Unpinned dependency versions (supply chain / reproducibility).
- **Files:** `ember-sandbox/docker-compose.yml`, `ember-sandbox/.env.example`, `ember-sandbox/seed/Dockerfile` (commit `8b0fa39`).
- **Details:**
  - `stashapp/stash:${STASH_IMAGE_TAG:-latest}`, and `.env.example` also sets `STASH_IMAGE_TAG=latest`.
  - `cloudflare/cloudflared:latest`
  - `python:3.12-alpine` is a moving tag with no digest.
  - `apk add --no-cache ffmpeg font-dejavu` installs unpinned package versions.

**Suggested fix:** Pin each image to an exact version **and** a digest (for example `stashapp/stash:v0.x.y@sha256:…`, `cloudflare/cloudflared:2026.x.y@sha256:…`, `python:3.12.x-alpine3.xx@sha256:…`). Default `STASH_IMAGE_TAG` to that version. Pin apk packages (`ffmpeg=<ver>`) or accept the risk knowingly. Add Dependabot (`package-ecosystem: docker`) so the pins get update PRs.

### F-4: No CSP, and third-party font loading (Low)

- **Type:** Missing hardening header / third-party request.
- **File:** `index.html` (lines 15 to 17 load `fonts.googleapis.com` / `fonts.gstatic.com`).
- **Details:** This is a static GitHub Pages site with no third-party scripts, so the risk is low. GitHub Pages cannot set response headers, though, so there is no CSP, and every visitor's IP is sent to Google. SRI does not work on Google Fonts CSS because it changes per browser.

**Suggested fix:** Self-host the four font families under `assets/fonts/`. Add `<meta http-equiv="Content-Security-Policy" content="default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; font-src 'self'">`, and loosen it only where an inline script requires it. Also add `<meta name="referrer" content="strict-origin-when-cross-origin">`.

### F-5: Personal hostname in commit metadata (Info)

- **Type:** Information disclosure.
- **Where:** Commit author email on commit `6de4448` and other hand-made commits contains a local machine name.
- **Suggested fix:** Run `git config --global user.email "<id>+<user>@users.noreply.github.com"` and turn on "Block command line pushes that expose my email" in GitHub settings. If you rewrite history for F-1, you can fix this at the same time with a `.mailmap` / `filter-repo --mailmap`.

### F-6: Stale feature branch is public (Info)

- **Type:** Unnecessary exposure of internal tooling.
- **Where:** `origin/claude/shared-ember-sandbox-docker-4vbaph` (commit `8b0fa39`), never merged into `main`.
- **Details:** A website repo publicly shows an internal test-server setup that has nothing to do with the website.
- **Suggested fix:** Move the sandbox to a private repo (for example `moonbase` or a new one), then delete the branch here. Fix F-2 and F-3 wherever it ends up.

## Not found

- No API keys, cloud credentials, private keys or tokens in any commit (gitleaks plus manual review).
- No `.env` file has ever been committed.
- No npm or PyPI dependencies, so there are no known-vulnerable packages.
- No third-party JavaScript on any page.

## Priority order

1. **Today:** F-1 step 1. Rotate any reused passwords and notify users.
2. **This week:** F-1 steps 2 and 3. Purge history and turn on secret scanning and push protection.
3. **Next:** F-6, then F-2 and F-3 in the sandbox's new home.
4. **When convenient:** F-4 and F-5.
