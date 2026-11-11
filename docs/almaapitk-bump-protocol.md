# almaapitk bump protocol (binding)

Every change to this repo's `almaapitk` pin follows this document, step by step. It is binding:
a bump that skips a step is not done. `CLAUDE.md` points here.

**Why it exists.** This repo is a production consumer of `almaapitk`. It runs on masedet, and
`main` and `prod` auto-deploy on a schedule with no second checkpoint. A bad bump on a
scheduled repo can fail silently in production. A bump is therefore a small, audited change
made inside this repo, never a one-line pin edit pushed from somewhere else.

## Ground rules

- **One repo at a time, from this repo.** The bump is done by a session working in this repo,
  using this repo's tests. Never as part of a batch across consumer repos, and never driven
  from the AlmaAPITK repo. An AlmaAPITK release ends by opening this repo's bump issue.
- **Trigger:** the issue "Bump almaapitk to `<version>` (pin → validate → main → prod)" in this
  repo. Bump to the current release directly; skip intermediate versions.
- **Agents never merge to `prod` or push to it.** The owner merges the PR into `main` and
  promotes `main` → `prod`.
- **No production writes during validation.** Live checks against PRODUCTION are read-only.
  Anything that writes to Alma, sends email or uploads files runs only against the SANDBOX,
  with `ALMA_PROD_API_KEY` unset, or not at all.
- **No real identifiers** (user IDs, MMS IDs, report paths with names, emails) in commits, PRs,
  issues or the audit. Use placeholders.

## Steps

### 1. Branch

`git checkout main && git pull && git checkout -b chore/almaapitk-<version>`.

### 2. Audit first: `docs/almaapitk-<version>-audit.md`

Write it before changing the pin. Earlier audits in `docs/` are the model. Sections:

- **(a) Usage surface.** Every `almaapitk` import and call in this repo, with `file:line`:
  classes, methods and arguments, exceptions caught, environment variables relied on.
- **(b) Upstream changes** from the version in `poetry.lock` to `<version>`: the AlmaAPITK
  `CHANGELOG.md` sections in between, plus anything the bump issue calls out. When the
  CHANGELOG is unclear, diff the wheels (`pip download almaapitk==<v> --no-deps` for both,
  then `diff -ru`).
- **(c) Per-symbol classification** of the usage surface: unchanged / changed but compatible
  / breaking. Every breaking entry names its fix.
- **(d) Repo-specific risks** listed under "This repo" below.
- **(e) Verdict:** SAFE, SAFE WITH CHANGES (list them), or BLOCKED (stop and report upstream).

### 3. Pin and lock

- Set `almaapitk = ">=<version>"`, keeping the pin's style and its comment.
- Run `poetry update almaapitk`, never a bare `poetry lock` that refreshes everything. Then run
  `poetry check --lock` and confirm `poetry.lock` resolves `almaapitk <version>`.
- No other package may move. If one must, list it in the audit with the reason.
- In the TAU sandbox, prefix Poetry commands with `POETRY_VIRTUALENVS_IN_PROJECT=false`. A
  `.venv` in the folder belongs to the WSL host.

### 4. Code changes (only if the audit requires them)

Keep them minimal, and give each one a test that fails without it. Don't add unrelated work
to the bump branch.

### 5. L2: this repo's tests

Run the commands under "This repo". All green, with no new skips.

### 6. L3: live check

Run the commands under "This repo" and record what ran and the result in the audit. If a
required L3 step can't run where you are (for example missing config), the PR says so and the
owner runs it before merging.

### 7. Pull request into `main`

- Commit the audit, pin, lock and any code changes:
  `chore(deps): bump almaapitk to >=<version> (#<issue>)`.
- The PR body links the audit and gives the L2 result and the L3 result (or what is left for
  the owner). It says `Refs #<issue>`, not `Closes`.
- Tick the issue's boxes that are actually done.
- The owner merges.

### 8. DevSandbox (masedet)

After the next scheduled auto-deploy of `main`, confirm at least one clean cycle on the
DevSandbox clone (see "This repo" for what clean means). Note it in the issue.

### 9. Prod

The owner merges `main` → `prod`; the next auto-deploy pulls the new version into Prod. After
the next Prod run, check its logs and output, then close the issue.

### Rollback

Pin `almaapitk==<previous>` on `prod`, run `poetry update almaapitk`, and push. The next
auto-deploy restores the previous version. Report the regression in AlmaAPITK with a failing
test (AlmaAPITK rule R10).

## This repo: Update_Alma_Digital_Collections

This is a **scheduled, unattended, writing** production job. It syncs Alma digital collection
membership to an Analytics report: it adds missing MMS IDs and removes extra ones. A bump that
made the report look empty or partial could remove members in bulk, so the Analytics read path
is the first thing to audit.

- **Usage surface:** `collection_sync.py` holds:
  - `AlmaAPIClient(environment)`
  - `Analytics.fetch_report_rows(report_path)`
  - `BibliographicRecords.get_collection_members(id, limit=, offset=)`, `add_to_collection` and
    `remove_from_collection`
  - `AlmaAPIError` with `status_code`, and the `400` + "already assigned" match

  `dry_test.py` uses `AlmaAPIClient` only. Check it with
  `grep -rn "from almaapitk\|status_code\|AlmaAPIError" collection_sync.py dry_test.py`.
- **Repo-specific risks for (d):**
  - Anything that could return fewer report rows or members than really exist: paging,
    truncation, stall handling.
  - Whether an Analytics failure aborts the run before any write. It must.
  - Error classes and status codes on add and remove.
  - The "already assigned" string match.
- **L2:** `poetry run pytest -q`. `tests/test_collection_sync.py` covers the diff and the safety
  guards.
- **L3:**
  - `dry_test.py` against SANDBOX, with `ALMA_PROD_API_KEY` unset, on a test collection that
    has members. Pass a report path too, so the Analytics read is exercised.
  - Or a read-only dry run against PRODUCTION (`dry_test.py` / dry-run mode, never a real sync).
- **Clean DevSandbox cycle:** one scheduled run completes, and its add and remove counts match a
  `dry_test.py` preview taken just before it.
