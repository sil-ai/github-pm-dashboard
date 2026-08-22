# Plan format

The canonical spec for the Plans tab. An agent authoring a Plan in any `sil-ai`
repo must follow this exactly. See `CONTEXT.md` for the vocabulary and
`docs/adr/` for why it works this way.

## Where a Plan lives

A Plan is a **GitHub issue labelled `plan`** in the repo where most of its work
happens, even when its Steps reach into other repos.

The label does not exist in most repos yet, and `gh issue create --label plan`
**fails** if the label is absent. Create it first — `--force` makes this a no-op
when it already exists:

```bash
gh label create plan --force --color BFD4F2 \
  --description "Ordered cross-repo plan tracked in the PM dashboard" \
  --repo sil-ai/<repo>
```

## Body

Prose first, then **one flat checklist**. Everything that is not a checklist
line becomes the Plan's collapsible Context in the dashboard, so put warnings,
constraints and rollback notes there.

```markdown
Splits `User` into `Account` + `Profile`. The migration is not reversible.
Do not run it before 17:00 UTC. Rollback: revert #412 and restore from the
pre-migration snapshot.

- [ ] Merge auth refactor <!-- repo:aqua-api ref:412 kind:merge -->
- [ ] Run migration 0043 on prod <!-- repo:aqua-api kind:migrate -->
- [ ] Deploy aqua-api <!-- repo:aqua-api kind:deploy -->
- [ ] Verify /health returns 200 <!-- repo:aqua-api kind:verify -->
- [ ] Merge client update <!-- repo:aqua-web ref:88 kind:merge -->
- [ ] Announce in #eng <!-- kind:manual -->
```

## Step lines

```
- [ ] <what to do> <!-- repo:<name> ref:<number> kind:<kind> -->
```

| Field  | Required | Meaning |
| ------ | -------- | ------- |
| `repo` | no | Repo the Step happens in, without the `sil-ai/` prefix. Omit for Steps that touch no repo. |
| `ref`  | no | The PR or issue **whose completion is this Step**, as a bare number in `repo`. Not any PR the Step merely mentions. Omit it when the PR does not exist yet. `repo` must be set too. |
| `kind` | yes | One of `merge`, `migrate`, `deploy`, `verify`, `manual`. |
| `by`   | never at authoring | Set only when a Step is ticked, to the GitHub login of the person asserting it. Written by the dashboard, or by an agent acting on that person's explicit instruction. |
| `at`   | never at authoring | Set alongside `by`. UTC, `%Y-%m-%dT%H:%M:%SZ`. |

Rules:

- **Flat list only.** Indented checklist items are flattened, so nesting buys
  nothing and misleads. Use one list; if a Plan needs phases, say so in the
  prose.
- **Order is the Plan.** Steps run top to bottom. The dashboard highlights the
  first unticked Step as "next up".
- **Never author a Step as `[x]`.** Done is a person's assertion, made by
  ticking. Leave out Steps that were already finished before the Plan existed.
- **`ref` must resolve.** A missing PR shows as a loud "ref not found" warning,
  not as a blank.
- **`ref` is the Step's own subject, never a mention.** "Revert #406" must not
  carry `ref:406` — #406 is already merged, so the dashboard would show "merged"
  beside a Step nobody has started. If the PR that does the reverting does not
  exist yet, omit `ref` and add it later.
- Keep Step text short enough to read in a row — detail goes in the prose.

## Kinds

| Kind      | Use for | Dashboard can observe it? |
| --------- | ------- | ------------------------- |
| `merge`   | A PR that must land | Yes, via `ref` |
| `migrate` | A schema or data change | No |
| `deploy`  | Shipping a service | No |
| `verify`  | Confirming something worked — a gate, not work | No |
| `manual`  | Anything else | No |

A merged PR is **never** ticked automatically. The dashboard shows "merged"
beside the unticked Step and waits for a person. See
`docs/adr/0002-done-is-asserted-not-observed.md`.

## Closing

A Plan leaves the tab when its issue is closed. At 5/5 the dashboard offers a
"Close plan" button; closing on GitHub works identically.
