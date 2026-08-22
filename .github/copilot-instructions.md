# Copilot Instructions — sil-ai PM Dashboard

The PM Dashboard is a **FastAPI** application that reports on project management
activity across the **sil-ai** GitHub org (weekly summaries, overdue/aging
issues, priorities, PR review status, per-repo status, and per-member tasks). It
is a single-module app (`dashboard.py`) that serves a Jinja2 page shell
(`templates/index.html`) plus a static front end (`static/app.js`, Tailwind via
CDN), and exposes `/api/*` JSON endpoints the front end fetches. Data comes from
the **GitHub `gh` CLI** (via `subprocess`), parallelized with a
`ThreadPoolExecutor`; responses are cached in a **SQLite** database
(`data/cache.db`). It runs under **Uvicorn** on **port 8050** and is deployed
behind nginx via `docker-compose.yml`.

When reviewing pull requests, focus on **route integrity**, **consistency with
the existing routes**, and **sound design / SOLID principles**. Use the guidance
below.

## 1. Route integrity

Every new or modified route must be complete and safe end to end:

- Is registered on the module-level `app = FastAPI()` with the matching method
  decorator. HTML pages declare `response_class=HTMLResponse` and render through
  `templates.TemplateResponse(request=request, name=...)` (or return
  `HTMLResponse`); data endpoints live under `/api/...` and return
  `JSONResponse`. Auth-state changes use `RedirectResponse`.
- Is declared `async def`. Because `gh` calls are blocking `subprocess` calls,
  they must not run directly on the event loop when fanned out — offload them to
  the `ThreadPoolExecutor` via `loop.run_in_executor(...)` and
  `await asyncio.gather(...)`, exactly as `api_repo_summaries`, `api_weekly`,
  `api_pr_status`, and `api_actions` do.
- Respects auth. `_AuthMiddleware` redirects unauthenticated requests to
  `/login`; only `/login`, `/logout`, and `/static` are exempt. Do not add new
  public routes or bypass the middleware. Password checks use
  `hmac.compare_digest`, and the session cookie is set `httponly` /
  `samesite="lax"` — preserve those flags.
- Invokes `gh` only through the `run_gh(args, timeout=...)` /
  `run_gh_json(args, timeout=...)` helpers, passing arguments as a **list**
  (never a shell string and never `shell=True`). User-supplied values such as
  `repo` or `username` arrive as path/query params and are interpolated into
  `gh` arguments — keep them as discrete list elements (e.g.
  `"--repo", f"sil-ai/{repo}"`), never spliced into a shell command, so there is
  no shell-injection surface.
- Sets an explicit `timeout=` on `gh` calls that fan out per-repo (the existing
  code uses 10–15s) so one slow repo cannot hang the whole request, and wraps
  per-repo `gh` calls in `try/except` that logs a warning and returns a safe
  default — matching `fetch_summary`, `fetch_commits`, `fetch_runs`, and
  `fetch_reviews`. `run_gh` raises `RuntimeError` on non-zero exit and
  `subprocess.run(..., timeout=)` raises on timeout; never let those propagate
  unhandled into a fan-out gather.
- Validates and parses inputs explicitly. Date params (`start`, `end`) are
  parsed with `datetime.strptime(..., "%Y-%m-%d")` and defaulted sensibly when
  empty, as in `api_weekly`. Endpoints that depend on external config must
  degrade gracefully (e.g. `api_summarize_commits` returns
  `JSONResponse({"error": ...}, status_code=503)` when `OPENAI_API_KEY` is
  unset; `api_display_names` returns `{}` when the file is missing).

## 2. Consistency with existing routes (same patterns)

New routes must match the established conventions — flag deviations:

- **Naming:** JSON endpoints are namespaced under `/api/...` with kebab-case
  paths (`/api/repo-summaries`, `/api/pr-status`, `/api/my-tasks/{username}`)
  and snake_case handler names prefixed `api_` (`api_repo_summaries`,
  `api_pr_status`). New HTML pages render templates from `templates/` and new
  static assets live in `static/`.
- **gh access:** always go through `run_gh` / `run_gh_json`. For structured
  `gh api` output use the `--jq` / `-q` flag to project fields inside `gh`
  rather than fetching whole payloads and filtering in Python, consistent with
  the existing queries. Scope every org query to `sil-ai` (`--owner sil-ai` or
  `--repo sil-ai/{repo}`).
- **Caching:** expensive aggregate endpoints cache through the SQLite
  `api_cache` table via `_api_cache_get(cache_url)` / `_api_cache_set(cache_url,
  result)`, keyed by a `cache_url` string built from the path and its params
  (see `api_weekly` and `api_repo_status`). Honor the same contract: serve fresh
  cache within `API_CACHE_FRESH`, mark `cached["_stale"] = True` between
  `API_CACHE_FRESH` and `API_CACHE_MAX_AGE`, treat a `fresh` query param as a
  cache bypass, and discard entries older than `API_CACHE_MAX_AGE`. The
  `summaries` table (via `_cache_get` / `_cache_set`, keyed by a content
  `sha256`) is the analogous pattern for OpenAI commit summaries.
- **Parallel fan-out:** when querying many repos/PRs, define a `fetch_*` inner
  function, run it through `ThreadPoolExecutor(max_workers=8)` (4 for the OpenAI
  path) + `loop.run_in_executor`, and `asyncio.gather` the results — do not loop
  with sequential blocking `gh` calls.
- **Active repos:** repo-wide endpoints derive their repo set from
  `get_active_repos()` (non-archived, updated within 90 days) rather than
  re-listing repos with bespoke filters.
- **Writes:** only the Plans endpoints write to GitHub, and they must go through
  `run_gh(..., token=GH_WRITE_TOKEN)` so writes use the least-privilege
  credential rather than the ambient read token. A write route returns 503 when
  `GH_WRITE_TOKEN` is unset, mirroring `api_summarize_commits` with no
  `OPENAI_API_KEY`. Body-rewriting writes (ticking a Step) must re-read the
  issue and verify the target line before `gh issue edit`, returning 409 rather
  than clobbering a concurrent edit — see
  `docs/adr/0001-plans-stored-as-github-issues.md`.
- **Plan state:** never infer a Step's `done` from GitHub. A merged PR is
  reported as live state next to an unticked Step; only a person's tick sets
  `done`. See `docs/adr/0002-done-is-asserted-not-observed.md`.
- **Dates:** format and age dates with the existing helpers (`days_ago`,
  `fmt_date`, `since_date`) instead of re-deriving the arithmetic.

## 3. Design patterns & SOLID principles

Review for maintainable, well-structured code:

- **Single Responsibility — separate fetching from rendering:** handlers should
  orchestrate (parse params → check cache → fetch via `gh` → shape result →
  return `JSONResponse`/`TemplateResponse`). Keep data shaping in helpers and
  keep presentation in the templates / `app.js`; flag handlers that mix
  unrelated concerns or grow into large monolithic procedures.
- **DRY:** flag duplicated `gh`-invocation, date-parsing, caching, or
  per-repo-fan-out logic that should reuse `run_gh`/`run_gh_json`, the
  `since_date`/`fmt_date`/`days_ago` helpers, the `_api_cache_*` functions, or
  `get_active_repos()`. Repeated `gh search issues`/`gh search prs` query blocks
  that differ only by parameters are candidates for a shared helper.
- **Isolated cache logic:** all cache reads/writes go through the `_api_cache_*`
  and `_cache_*` helpers and the schema created in `_init_cache_db()`. Do not
  open ad-hoc `sqlite3.connect(...)` calls inside handlers or scatter raw SQL
  across the module; extend the helpers instead.
- **Open/Closed:** prefer parametrizing behavior through query params with
  sensible defaults (as `api_weekly` / `api_repo_status` do with
  `start`/`end`/`fresh`) over branching that requires touching many call sites.
- **Consistency of contracts:** identical concepts should have identical JSON
  shapes and keys across endpoints (e.g. the `repository`/`title`/`url`/
  `assignees` shape returned by the `gh search` endpoints, and the `_stale`
  flag on cached responses), so `app.js` can consume them uniformly.

## 4. What NOT to flag

- This repo has **no Python linter/formatter configured** (no flake8, black,
  isort, ruff, or pre-commit; the only workflow, `clean-branches.yml`, just
  prunes stale branches). Style nits aside, do still flag genuine correctness,
  security (especially `gh`/`subprocess` argument handling), and consistency
  issues — but keep purely cosmetic formatting comments to a minimum since
  nothing enforces them.
- Pre-existing patterns that the PR merely follows (review the diff, not the
  whole module's legacy choices).
- The Tailwind-via-CDN setup, the inline `_LOGIN_HTML` template, and generated/
  runtime artifacts under `data/` (e.g. `cache.db`) and gitignored files
  (`.env`, `display_names.json`).
- The Plans tab hiding `#range-controls`, and the Plan list being cached while
  Plan bodies are not — both are deliberate (a stale checklist can get a
  migration run twice).

Keep findings focused and actionable. Prioritize correctness, security
(no shell injection via `gh`, intact auth), and consistency over stylistic
preferences.
