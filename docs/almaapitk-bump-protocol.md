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

After the next auto-deploy of `main`, run the repo's DevSandbox check on masedet (see "This
repo"). If L3 in step 6 already ran there, on the deployed `main`, it counts. Note the result in
the issue.

### 9. Prod

The owner merges `main` → `prod`; the next auto-deploy pulls the new version into Prod. After
the next Prod run, check its logs and output, then close the issue.

### Rollback

Pin `almaapitk==<previous>` on `prod`, run `poetry update almaapitk`, and push. The next
auto-deploy restores the previous version. Report the regression in AlmaAPITK with a failing
test (AlmaAPITK rule R10).


## This repo: Update_Alma_Digital_Collections

This is a **scheduled, unattended, writing** production job. For each task in `config.yml` it
reads one or more Analytics reports and a digital collection's members, then adds the missing
MMS IDs and **removes** the members that are not in the reports. A bump that made a report or
the member list look shorter than it is could add or remove members in bulk. Treat every bump
as high-risk.

- **Usage surface** (line numbers as of this document; re-check them in the audit):
  - `collection_sync.py:27`: `from almaapitk import AlmaAPIClient, Analytics,
    BibliographicRecords, AlmaAPIError`.
  - `AlmaAPIClient(environment)`, positional only, key from `ALMA_SB_API_KEY` /
    `ALMA_PROD_API_KEY` (`main()`, about line 478); `client.logger` (about line 162).
  - `Analytics.fetch_report_rows(report_path)`, default paging; rows keyed `Column0`,
    `Column1`, … (`get_mms_ids_from_report`, `extract_mms_ids`).
  - `BibliographicRecords.get_collection_members(id, limit=100, offset=)`, read through
    `.json()["total_record_count"]` and `["bib"][]["mms_id"]` (`get_collection_mms_ids`).
  - `BibliographicRecords.add_to_collection(id, mms_id)` and `remove_from_collection(id,
    mms_id)`: the two writes.
  - `AlmaAPIError`: `e.status_code == 400` plus the text "already assigned" on add (counts as
    success); any `AlmaAPIError` on add or remove is logged and the run continues; in `main()` it
    exits 1.
  - Logger names `almapi.api_client`, `almapi.bibs`, `almapi.admin` get the archive-log handler
    (`main()`, about line 459).
  - `dry_test.py` uses `AlmaAPIClient(environment)` and the same `AlmaCollectionManager`.

  Check it with
  `grep -rn "almaapitk\|AlmaAPIError\|status_code\|almapi\.\|self\.bibs\.\|self\.analytics\." collection_sync.py dry_test.py`.
- **Repo-specific risks for (d):**
  - Anything that could return fewer report rows or collection members than really exist:
    Analytics paging and resumption tokens, truncation or row caps, stall handling, member
    paging past 100, a changed `.json()` shape. Fewer report rows means removals; fewer members
    means re-adds.
  - Whether every Analytics failure still raises before any write. The guards in
    `get_mms_ids_from_reports` and `plan_sync` rely on an exception or an empty / `Column1`-less
    result; a new failure mode that returns partial rows quietly would get past them.
  - The error class and `status_code` on add and remove for 400/401/429/5xx and timeouts, and
    whether the "already assigned" 400 still reaches the string match.
  - Retries: an add (POST) must not be retried in a way that double-posts; a timeout on a
    write must still surface as an `AlmaAPIError` (or the run's handling must be checked).
  - The logger names above, and whether the Analytics domain logs under a name the archive log
    does not capture.
  - Anything that could put the API key into log text past `RedactingFormatter`.
  - The `AlmaAPIClient(environment)` signature and the env-var key lookup.
- **L2:** `poetry run pytest -q` (26 tests at the time of writing). `tests/test_collection_sync.py`
  covers the diff and the empty / malformed / failed-report guards with fake almaapitk domains;
  `tests/test_redaction.py` covers log redaction. Both must stay green. There is no CI, so run
  them locally. These tests use fakes, so they do not detect a changed almaapitk signature or
  response shape; that is what the audit (step 2) and L3 are for.
- **L3 (read-only; never a real sync against PRODUCTION):** `dry_test.py` is the live check. It
  only reads (collection members and Analytics rows) and prints the plan; it never calls add or
  remove.
  - **Analytics reads only work against PRODUCTION.** Against the Sandbox,
    `Analytics.fetch_report_rows` fails on Alma's side (`obiLogin is null`). So a full preview
    (members + report + diff) is always a read-only PRODUCTION run. The Sandbox is a copy of
    Production, so a production task's `collection_id` also exists there.
  - Run both, using one production task's collection ID and report path(s):
    1. SANDBOX, with `ALMA_PROD_API_KEY` unset:
       `poetry run python dry_test.py --environment SANDBOX --collection-id <collection_id> --report-path <report_path>`.
       This checks member reads and paging (pick a collection with more than 100 members). The
       report read is expected to fail, and the pass condition is that the guard reports "the
       real run would make no changes".
    2. PRODUCTION, read-only:
       `poetry run python dry_test.py --environment PRODUCTION --collection-id <collection_id> --report-path <report_path>`,
       or on masedet `poetry run python dry_test.py --config config.yml --task <task_name>`.
       This is what exercises `Analytics.fetch_report_rows` and the diff.
  - Pass: no errors; the member count equals the collection's total; the report count is
    plausible; the add and remove counts match a preview taken on the previous version (run it
    before switching, or on the Prod clone). A large unexplained remove count is a failure.
  - Record counts only in the audit. `dry_test.py` prints sample MMS IDs; don't copy them.
  - Watch out: with `--config`, the environment comes from the config file and
    `--environment` is ignored; a config without `environment` means PRODUCTION (issue #16).
    That is still read-only for `dry_test.py`, but check which one you are on.
  - `collection_sync.py --dry-run` is not a live check: it only lists tasks and makes no API
    calls.
  - The add and remove calls are not exercised live by L3. A SANDBOX sync can't exercise them
    either: its report read fails, so the guard makes no changes. Their coverage is the unit tests
    plus the audit's error-class review (step 2).
- **DevSandbox check (masedet):** **not determined from the repo.** The Task Scheduler command
  and the real `config.yml` live on masedet, so this document cannot say whether the DevSandbox
  clone has a scheduled task, or whether its `config.yml` targets SANDBOX or PRODUCTION. Until
  the owner records it here, on masedet:
  1. In `D:\Scripts\DevSandbox\Update_Alma_Digital_Collections`: `git log -1` shows the merged
     `main`, and
     `poetry run python -c "import almaapitk; print(almaapitk.__version__)"` shows the new
     version.
  2. Check which `environment` its `config.yml` sets. If it is PRODUCTION or missing, **do not
     start a sync from this clone**; it would write to production.
  3. Run the L3 `dry_test.py` preview from this clone. If a scheduled DevSandbox task exists,
     also check its next log (`logs/alma_manager_<timestamp>.log`): every task completes, no
     `Alma API error` or `Unexpected error`, and the add and remove counts match the preview.
- **More:** `README.md` (config, CLI flags, edge cases), `CLAUDE.md`, the earlier audit
  `docs/almaapitk-audit.md` (0.3.1 → 0.4.6, written against the old script).
