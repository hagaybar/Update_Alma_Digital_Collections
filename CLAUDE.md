# CLAUDE.md — Update Alma Digital Collections

Keeps Alma digital collections' membership in sync with Alma Analytics reports: for each task in
`config.yml`, MMS IDs in the reports but not the collection are added, members not in the reports
are removed. It is a **scheduled, unattended job on masedet that writes to production Alma**
(`main` → DevSandbox, `prod` → Prod; the Task Scheduler command and real `config.yml` live on
masedet, not in this repo). Usage for humans: `README.md`.

## Layout
- `collection_sync.py`: everything. `plan_sync` (the diff), `extract_mms_ids` (report rows →
  MMS IDs), `AlmaCollectionManager` (reads, add, remove, sync), `ConfigManager`,
  `RedactingFormatter`, `main()` (CLI).
- `dry_test.py`: read-only preview; prints the plan with sample IDs. Imports from `collection_sync`.
- `tests/`: unit tests with fake almaapitk domains, no network. `config_sample.yml`: config template.
- `docs/almaapitk-audit.md`: the 0.3.1 → 0.4.6 audit (historical: written against the old
  `AlmaCollectionManager_6.py`).

## Commands
- Install: `poetry install`. Tests: `poetry run pytest -q` (26 tests). There is no CI.
- Preview (read-only): `python dry_test.py --config config.yml --task <name>`, or
  `--collection-id <id> --report-path <path> --environment SANDBOX`.
- Live sync: `python collection_sync.py [-t <task>]...` — **writes**. `--dry-run` only lists the
  tasks it would run; it does not compute a diff. Use `dry_test.py` to see the plan.
- Deploy: merge to `main` → DevSandbox; the owner merges `main` → `prod`. The masedet auto-deploy
  pulls and runs `poetry install` on its next scheduled run.

## Rules
Enforced by code:
- A failed, empty or malformed report (no rows, a row without `Column1`, no MMS IDs, no report
  paths) leaves the collection untouched; all reports are fetched before any write
  (`get_mms_ids_from_reports`, `plan_sync`; `tests/test_collection_sync.py`).
- MMS IDs come from `Column1` only (`MMS_ID_COLUMN`) and are deduplicated before any API call.
- "already assigned" 400 on add counts as success; other add/remove errors are logged and the run
  continues (`add_to_collection`, `remove_from_collection`).
- Console and log output pass through `RedactingFormatter`, which scrubs `ALMA_SB_API_KEY` /
  `ALMA_PROD_API_KEY` values and labelled credentials (`tests/test_redaction.py`).
- `config.yml` is gitignored; commit only `config_sample.yml`.

Written only:
- **A config without `environment` runs against PRODUCTION** (`get_environment()` default), and
  a plain run writes. Always set `environment: SANDBOX` in a test config, and preview with
  `dry_test.py` first. Tracked in #16; do not change these defaults without the owner, since the
  masedet Task Scheduler command depends on them.
- Production writes need a `dry_test.py` preview and the owner's OK.
- Any change to the `almaapitk` pin follows the bump protocol (one bump at a time, with an audit
  doc); it lands as `docs/almaapitk-bump-protocol.md` with PR #13 (almaapitk 0.7.0). A pin bump
  reaches Prod on the next auto-deploy after the owner merges to `prod`.
- Behaviour changes come with a test in `tests/` that fails without them.

## Where to look
- Alma work: load `alma-digital` (digital collections and representations) and `alma-api-expert`
  (auth, errors, paging, code tables); `alma-bibs-inventory` for bib lookups.
- `README.md`: config format, CLI flags, edge cases. Open issues: #11 (failure-mode audit),
  #12 (almaapitk 0.7.0 bump), #16 (production defaults).
- `AGENTS.md`: the reviewer's brief (Codex reviews, Claude builds).
