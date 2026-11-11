# almaapitk 0.5.1 → 0.7.0 compatibility audit

**Date:** 2026-11-11 · **Issue:** #12 · **Protocol:** `docs/almaapitk-bump-protocol.md`
**Method:** AlmaAPITK `CHANGELOG.md` sections 0.6.0 and 0.7.0, read against this repo's usage
surface. The L1 contract tests for BibliographicRecords collections and Analytics in AlmaAPITK
pass on 0.7.0.

**Verdict: SAFE.** No code change.

## (a) Usage surface (`collection_sync.py`)

| Symbol | Where |
|---|---|
| `AlmaAPIClient(environment)` | l.478 (also `dry_test.py`) |
| `Analytics(client).fetch_report_rows(report_path)` | l.161, l.269 |
| `BibliographicRecords(client).get_collection_members(id, limit=, offset=)` | l.160, l.173–180 |
| `add_to_collection(id, mms_id)`; `except AlmaAPIError` with `status_code == 400` and "already assigned" | l.205–209 |
| `remove_from_collection(id, mms_id)`; `except AlmaAPIError` | l.239–241 |
| `except AlmaAPIError` at top level | l.523 |

## (b) Upstream changes that touch this surface

- **0.6.0, #229.** `fetch_report_rows()` raises `AlmaAnalyticsStalledError` (an `AlmaAPIError`)
  after 20 pages or 600 s with no new rows, instead of looping forever. `max_pages=None` by
  default, so there's no truncation.
- **0.6.0, #208.** A 5xx that survives the retries raises `AlmaServerError` (an
  `AlmaAPIError`), not `RetryError`. Analytics 500s are not retried.
- **0.6.0, #196.** Timeouts raise `AlmaTimeoutError` (an `AlmaAPIError`). `Retry-After` waits
  are capped at 120 s.
- **0.7.0, #205.** 401, 429 and 5xx outrank mapped codes. This repo catches only
  `AlmaAPIError`, so there is no effect.
- The collection methods are unchanged since 0.4.6 (L1 contract tests).

## (c) Classification

| Symbol | Status |
|---|---|
| `AlmaAPIClient(environment)` | unchanged |
| `fetch_report_rows(report_path)` | compatible; a stalled report now raises instead of hanging |
| `get_collection_members` / `add_to_collection` / `remove_from_collection` | unchanged |
| `status_code == 400` + "already assigned" | unchanged (#205 leaves 400 alone) |

## (d) Repo-specific risks

- **Partial data leading to bulk removal:** no new path. Every new failure mode (stall, server
  error, timeout) is an `AlmaAPIError` raised while the report is being read, before any add or
  remove. The run aborts without writing.
- **Duplicate adds:** POST is still not retried, and "already assigned" is still treated as
  done.

## (e) Result

- **Lock:** `poetry update almaapitk` moved almaapitk 0.5.1 → 0.7.0 only.
- **L2:** 26 passed.
- **L3 (partial):** `dry_test.py` on SANDBOX, with `ALMA_PROD_API_KEY` unset, read one collection
  cleanly on 0.7.0. That collection had 0 members and no report path was given, so the Analytics
  read and the diff were not exercised. The owner runs `dry_test.py` with a populated collection
  and a report path before merging.
