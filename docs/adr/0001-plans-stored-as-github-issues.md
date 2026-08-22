# Plans are stored as GitHub issues in the repo where the work happens

A Plan needs to be writable by an agent working in any repo and by a person
ticking a box in this dashboard, and it needs to outlive container rebuilds. We
store each Plan as an issue labelled `plan` in the repo where most of its work
happens, with Steps as a flat GitHub task list and per-Step metadata in a
trailing HTML comment (`<!-- repo:x ref:n kind:k by:who at:when -->`).

## Considered options

- **SQLite in `data/`** — instant writes, but the volume is gitignored and
  unbacked, there is no history, and an agent in another repo would need a new
  authenticated HTTP write path.
- **Markdown files in this repo** — reviewable in a PR, but a tick would have to
  become a git commit, which means commit noise and, once auto-deploy lands, a
  container restart on every checkbox click.
- **Hybrid: markdown for Steps, SQLite for ticks** — avoids the deploy problem,
  but two stores drift and editing the file orphans tick state.
- **A central Plan registry in this repo's issues** — one home and one trivial
  query, rejected because a Plan should sit next to the code it concerns and
  notify that repo's watchers.

## Consequences

- Discovery is `gh search issues --owner sil-ai --label plan`, which costs the
  scarce search budget (30/min vs 5000/min core). The Plan list is cached; Plan
  bodies are always fetched fresh, because a stale rollout checklist can cause a
  migration to be run twice.
- `gh issue create --label plan` fails when the label does not exist in that
  repo, so authoring must run `gh label create plan --force` first.
- GitHub has no endpoint for toggling one checkbox, so a tick rewrites the whole
  issue body. Ticks re-read the body and verify the target line before writing,
  and refuse rather than clobber a concurrent edit.
- The issue stays a normal tickable checklist on github.com, which is the
  deliberate reason metadata hides in HTML comments rather than a YAML block.
- A Plan spanning three repos has to pick one arbitrarily as its home, so the
  dashboard shows the union of the repos its Steps touch rather than that home.
- Ticking writes to org issues, so it uses a dedicated fine-grained token scoped
  to Issues: Read+Write and nothing else — the dashboard's single shared password
  must not front a `repo`-scoped token.
