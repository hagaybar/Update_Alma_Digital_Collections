# almaapitk 0.3.1 → 0.4.6 Compatibility Audit

> **Historical.** Written against `AlmaCollectionManager_6.py`, which has since become `collection_sync.py`; Analytics now goes through `almaapitk.Analytics` instead of direct `requests`. Line numbers below refer to the old file.

**Date:** 2026-06-02
**Scope:** Does bumping `almaapitk` from the current floor `>=0.3.1` to `>=0.4.6` (latest PyPI release) break this repo — a **scheduled, unattended, _mutating_ production job** that adds/removes MMS IDs in Alma Digital Collections (`AlmaCollectionManager_6.py`)? A bad bump fails **silently in prod**, so the bar is "prove the surface is preserved," not "looks fine."
**Method:** Read-only. Both versions obtained via `pip download almaapitk==<v> --no-deps` and unzipped to `/tmp/almaapitk_audit/src031` and `/tmp/almaapitk_audit/src046`; compared per-surface-file. The 0.4.6 public surface was introspected with the project interpreter (`PYTHONPATH=src046 python -c ...`): imports resolve, signatures match, `AlmaAPIError('x', status_code=400).status_code == 400`. No project files were modified by the audit; nothing was installed into `.venv`. Mirrors `Fetch_Alma_Analytics_Reports/docs/almaapitk-0.4.6-audit.md` and `Alma-RS-lending-request-automation/docs/almaapitk-audit.md`, adapted for **this repo's big jump** (0.3.1 → 0.4.6 crosses 0.4.3 and 0.4.5).

> **PyPI release status (checked 2026-06-02):** `pip index versions almaapitk` → `0.4.6, 0.4.5, 0.4.3, 0.3.1`. 0.4.6 is the latest installable.

**Verdict: SAFE.** Every `almaapitk` symbol this repo imports, constructs, calls, reads, or catches is preserved in 0.4.6 with a compatible signature and inheritance. **All three collection methods this repo's write/read path depends on — `get_collection_members`, `add_to_collection`, `remove_from_collection` — are byte-identical across 0.3.1 → 0.4.6.** The behavior deltas that reach this repo are improvements or no-ops: (1) 0.4.6 **adds** a retry layer for GET/PUT/DELETE that 0.3.1 lacked entirely — strictly safer for this repo's reads (`get_collection_members`) and idempotent removes (DELETE); the non-idempotent `add` (POST) is deliberately **not** retried, which is the correct posture for a job that creates collection memberships; (2) per-request timeout drops 300s → 60s — ample for single-item add/remove and `limit≤100` member pages; (3) logging is quieter by default (no log file, no request/response bodies, PII redacted) — and **this repo wires its own logging regardless**, so the change is cosmetic here. One bump-independent, Alma-text-dependent note (the "already assigned" 400 string match) is documented in §E.

---

## (a) Usage surface — the entire almaapitk contract this repo depends on at runtime

`AlmaCollectionManager_6.py` is the production entry point (run unattended on the masedet box). `dry_test.py` is a manual preview tool that imports the same classes. The complete almaapitk surface:

| Surface element | Location (`AlmaCollectionManager_6.py`) | Detail |
|---|---|---|
| Import | line 31 | `from almaapitk import AlmaAPIClient, BibliographicRecords, AlmaAPIError` |
| Client constructor | line 468 | `AlmaAPIClient(environment)` — single positional arg (`"SANDBOX"` or `"PRODUCTION"`, from `config.yml`). Relies on the env-var key fallback. |
| Env var (read indirectly) | — | `AlmaAPIClient` reads **`ALMA_SB_API_KEY`** (SANDBOX) / **`ALMA_PROD_API_KEY`** (PRODUCTION) from the environment when no `api_key=` is passed. The repo never reads the value itself. |
| Domain construction | line 54 | `BibliographicRecords(client)` (stored as `self.bibs`) |
| Logger handle | line 55 | `self.logger = client.logger` — the repo then calls `.info()`, `.debug()`, `.warning()` on it. |
| **Member read (GET)** | lines 68, 91–95 | `self.bibs.get_collection_members(collection_id, limit=1)` (count probe) and `(collection_id, limit=100, offset=offset)` (pagination). Reads `response.json()["total_record_count"]` (line 70) and `response.json().get("bib", [])` → `bib["mms_id"]` (lines 96–98). |
| **Add (WRITE / POST)** | line 130 | `self.bibs.add_to_collection(collection_id, mms_id)` |
| **Remove (WRITE / DELETE)** | line 175 | `self.bibs.remove_from_collection(collection_id, mms_id)` |
| Error introspection | lines 139–146 | `except AlmaAPIError as e: if e.status_code == 400 and "already assigned" in str(e).lower():` — relies on `AlmaAPIError.status_code` and the message string. |
| Error introspection | line 184 | `except AlmaAPIError as e:` on remove — logs a warning and continues. |
| Top-level catch | line 513 | `except AlmaAPIError as e:` in `main()` → log + `exit(1)`. |
| Client attrs (Analytics path) | lines 210, 218 | `self.client.base_url` and `self.client.api_key` — used by `get_mms_ids_from_report`, which calls the Alma **Analytics** API with **direct `requests`**, NOT through almaapitk. |

**Notes on the surface:**
- The Analytics report fetch (`get_mms_ids_from_report`, lines 191–265) does **not** go through almaapitk — it builds its own `requests.get` against `{client.base_url}/almaws/v1/analytics/reports` using `client.api_key`. So the only almaapitk attributes it needs are `base_url` and `api_key` (both present and unchanged — see §C). The bump cannot affect the Analytics path beyond those two attributes continuing to exist.
- `get_collection_members` returns whatever `client.get(...)` returns. In **both** versions that is an `AlmaResponse` wrapper exposing `.json()` (0.3.1 `AlmaResponse.json()` → `self._response.json()`; 0.4.6 same, with result caching added). The `total_record_count` / `bib[].mms_id` shape is the **Alma API's** JSON contract, passed through untouched by almaapitk — not something the bump can change.
- The L1 contract methods named in the rollout brief (`get_collection_members`, `add_to_collection`, `remove_from_collection`) are exactly this repo's three methods. They are pinned upstream; this audit re-verifies them at the source level for the 0.3.1 → 0.4.6 distance.

---

## (b) 0.3.1 → 0.4.6 diff, restricted to files this repo touches

| File / symbol | Status across 0.3.1 → 0.4.6 | Relevance to this repo |
|---|---|---|
| `domains/bibs.py` → `get_collection_members`, `add_to_collection`, `remove_from_collection` | **byte-identical** (method bodies + signatures) | The entire read + write path. Verified by extracting and diffing the three method bodies; identical. |
| `AlmaResponse.json()` / `.data` / `.text` | preserved | 0.3.1: `.json()` returns `self._response.json()`. 0.4.6: same contract, body cached on first parse so repeated `.json()`/`.data` access doesn't re-parse; still raises on non-JSON. The repo's `response.json()` reads are unaffected. |
| `__init__.py` top-level exports | preserved + additive | `AlmaAPIClient`, `BibliographicRecords`, `AlmaAPIError` all still in `__all__` and the lazy-export map → `almaapitk._internal`. 0.4.6 adds typed `AlmaAPIError` subclasses and other domains; nothing removed. |
| `AlmaAPIClient.__init__` | **compatible** | 0.3.1: `__init__(self, environment='SANDBOX')`. 0.4.6: `__init__(self, environment='SANDBOX', *, api_key=None, max_retries=3, backoff_factor=1.0, retry=None, timeout=None, region='EU', host=None)`. `environment` is still the **first positional**; every new parameter is **keyword-only with a default**, so `AlmaAPIClient(environment)` is unchanged. |
| `client.base_url` | preserved (default EU) | 0.3.1: hard-coded `"https://api-eu.hosted.exlibrisgroup.com"`. 0.4.6: `REGION_HOSTS["EU"]` with `DEFAULT_REGION="EU"` → **identical default value**. The repo constructs the client with no `region=`/`host=`, so `base_url` is the EU host in both — the Analytics direct-`requests` call (line 210) is unaffected. |
| `client.api_key` | preserved | 0.3.1: `os.getenv('ALMA_SB_API_KEY' / 'ALMA_PROD_API_KEY')`. 0.4.6: `self._api_key_arg or os.getenv(DEFAULT_API_KEY_ENV_VAR[environment])` — same env vars, same attribute. Used at line 218. |
| `client.logger` (`AlmaLogger`) | preserved | `get_logger('api_client', ...)` in both. `AlmaLogger` exposes `.info/.debug/.warning/.error(message, **kwargs)` in both versions. The repo's `self.logger.info(f"...")` etc. (positional message, no kwargs) work unchanged. |
| `AlmaAPIError` | **compatible** | 0.3.1: `__init__(self, message, status_code=None, response=None)`. 0.4.6: `__init__(self, message, status_code=None, response=None, tracking_id=None, alma_code="")` — extra args are optional with sentinels; the legacy positional path `(message, status_code, response)` is preserved. `.status_code` attribute present in both. `class AlmaAPIError(Exception)` in both. |
| Error-raising path (`_handle_response`) | preserved | Both versions raise `AlmaAPIError(error_msg, status_code, response)` on a non-success status, extracting `errorList.error[0].errorMessage` into the message. So `add`/`remove` still raise `AlmaAPIError` on failure, and `e.status_code` is populated. |
| Logger names | preserved | `logging.getLogger(f"almapi.{domain}")` in both → `almapi.api_client`, `almapi.bibs`, `almapi.admin`. The repo's `main()` attaches its own file handler to exactly these names (lines 449–450); they still exist. 0.4.6 adds a shared `almapi` parent for level control (additive). |

**New in 0.4.6, unused by this repo (additive only):** typed `AlmaAPIError` subclasses (`AlmaAuthenticationError`, `AlmaResourceNotFoundError`, `AlmaRateLimitError`, `AlmaServerError`, `CredentialError`, …), `domains/configuration.py`, `domains/electronic.py`, the `almaapitk/testing/` package (test rails — see §F), and client retry/timeout/region keyword args. None are imported or referenced here.

---

## (c) Breaking changes affecting this repo

**None.** Per-symbol classification of the surface in §(a):

| Symbol | 0.4.6 status |
|---|---|
| `import AlmaAPIClient, BibliographicRecords, AlmaAPIError` (line 31) | **unchanged** — all three exported from top-level `almaapitk`; same names, same inheritance (`AlmaAPIError(Exception)`). Verified by live import against 0.4.6. |
| `AlmaAPIClient(environment)` (line 468) | **unchanged** — `environment` still first positional; all new params keyword-only with defaults. |
| `ALMA_SB_API_KEY` / `ALMA_PROD_API_KEY` contract | **unchanged** — still the SANDBOX/PRODUCTION fallbacks. On a *missing* key the exception type changed (0.3.1 raised at construction; 0.4.6 raises `CredentialError`, a subclass of `ValueError`). The repo does not catch it at construction, so it propagates and the scheduled job fails **loudly** — correct for an unattended job, identical observable outcome (process exits non-zero) in both. |
| `BibliographicRecords(client)` (line 54) | **unchanged** |
| `self.logger = client.logger` + `.info/.debug/.warning` | **unchanged** — `AlmaLogger` exposes all three in both versions. |
| `get_collection_members(...)` → `.json()["total_record_count"]` / `["bib"][i]["mms_id"]` (lines 68, 91–98) | **unchanged** — method byte-identical; `AlmaResponse.json()` preserved; JSON shape is the Alma API's, passed through. |
| `add_to_collection(collection_id, mms_id)` (line 130) | **unchanged** — byte-identical; POSTs `{"mms_id": ...}` to `bibs/collections/{id}/bibs`. |
| `remove_from_collection(collection_id, mms_id)` (line 175) | **unchanged** — byte-identical; DELETEs `bibs/collections/{id}/bibs/{mms_id}`. |
| `AlmaAPIError.status_code` (lines 141, 184, 513) | **unchanged** — attribute preserved; `== 400` / `== <code>` comparisons work. |
| `self.client.base_url`, `self.client.api_key` (lines 210, 218) | **unchanged** — both attributes present; `base_url` defaults to the EU host in both. |

No line in `AlmaCollectionManager_6.py` or `dry_test.py` needs remediation.

---

## (d) Write-path behavior — retry & timeout (special to this _mutating_ repo)

This is the area with operational meaning for a job that **adds and removes** collection memberships. The big-jump framing in the rollout brief ("POST is no longer auto-retried on 5xx") is calibrated for the 0.4.5 → 0.4.6 step; for **this repo's actual 0.3.1 → 0.4.6 jump it is essentially a non-event**, because:

- **0.3.1 had NO retry layer at all.** Every verb went through bare `requests.get/post/delete(..., timeout=300)` with no `urllib3` `Retry` and no mounted `HTTPAdapter`. A transient `429`/`5xx` on any call surfaced **immediately** as an `AlmaAPIError` (via `_handle_response`).
- **0.4.6 ADDS** a mounted `HTTPAdapter` with `Retry(total=3, backoff_factor=1, status_forcelist=(429,500,502,503,504), allowed_methods={"GET","PUT","DELETE"})`.

Net effect for this repo, per verb:

| This repo's call | Verb | 0.3.1 (no retries) | 0.4.6 (retries on GET/PUT/DELETE) | Assessment |
|---|---|---|---|---|
| `get_collection_members` (count + pagination) | GET | no retry; transient 5xx → immediate error | **retried up to 3× with backoff** | **Improvement** — a flaky read no longer aborts the whole sync run. |
| `remove_from_collection` | DELETE | no retry | **retried up to 3×** | **Improvement & safe** — DELETE of a collection membership is idempotent (removing an already-removed bib is a no-op / handled error), so retry cannot duplicate state. |
| `add_to_collection` | POST | no retry | **NOT retried** (POST excluded) | **Unchanged & correct** — add is non-idempotent; not retrying avoids a duplicate-add-on-lost-response. A transient 5xx on add raises `AlmaAPIError`, caught at lines 139–146 → logged as a per-item failure, loop continues; the item is re-added on the **next scheduled run** because the sync recomputes the diff from the report each run. No data loss, no duplicate. |

**Timeout:** 300s (0.3.1) → 60s default (0.4.6), per request. This repo's requests are all small: single-item add/remove, and member pages capped at `limit=100`. 60s is ample. If a pathological collection page ever timed out, the remedy is bump-independent (`AlmaAPIClient(environment, timeout=...)`, a keyword arg present in 0.4.6). **No code change required.**

The Analytics fetch (§A) uses its own `requests.get` with **no timeout** and no retries in both versions — entirely outside almaapitk's adapter — so the bump does not change it.

**No code change required for the write path.** The new default (retry reads/removes, don't retry adds) is the recommended posture for this sync job.

---

## (e) Logging / PII considerations

`AlmaCollectionManager_6.py`'s `main()` (lines 429–453) builds its **own** console + timestamped-file handlers and attaches the file handler to `almapi.api_client`, `almapi.bibs`, `almapi.admin` so the toolkit's INFO lines land in the repo's archive log. This wiring is **independent of almaapitk's own logging defaults**, so the 0.4.6 logging changes are cosmetic for this repo:

**What the bump changes (all in the repo's favor):**
- 0.3.1's logging config defaulted to `console: True, file: True` with `log_requests/log_responses: True` and some domain levels at DEBUG — i.e. almaapitk **dropped its own `logs/api_requests/<date>/api_client.log` file** and logged request/response bodies. (The two stale `logs/api_requests/.../api_client.log` files in the working tree are 0.3.1-era artifacts; they are `*.log`-gitignored.)
- 0.4.6 flips defaults to `file: False`, `log_bodies: False`, and normalizes domain levels to INFO. So after the bump, almaapitk **no longer writes its own side log file** and **no longer logs bodies** unless explicitly opted in. PII surface shrinks.
- The repo's archive log is unaffected (it is produced by the repo's own `FileHandler`, not almaapitk's).

**Note (bump-independent, low risk):** the repo's "already in collection" handling at line 141 matches `e.status_code == 400 and "already assigned" in str(e).lower()`. The 400 status comes from almaapitk (preserved). The **message text** ("already assigned") is Alma's `errorMessage`, surfaced verbatim by `_handle_response` in both versions — so this match is **Alma-text-dependent, not almaapitk-version-dependent**. The bump does not change it; flagged only because the live SANDBOX smoke (§F) is a good moment to confirm a duplicate add is still classified as success rather than counted as an error.

This repo handles **bib/MMS IDs and collection IDs**, not patron PII, so the patron-record concerns from the resource-sharing repo's audit do not apply here. Per the repo's hard rules, no real collection/MMS IDs appear in this document — only placeholders and structural descriptions.

---

## (f) PROD-write safety & the L1/L2/L3 test strategy

**The "PROD-write safety lock" is a _test-harness_ feature, not a runtime change.** 0.4.6 ships an `almaapitk/testing/` package (`guards.py`, `transport.py`, `flaky.py`, `pytest_plugin.py`, …) — rails that wrap a `requests.Session` so non-GET verbs raise before I/O when a workflow is PRODUCTION-targeted. **None of it touches the production `AlmaAPIClient` this repo runs**; the scheduled job's runtime behavior is identical whether or not those helpers exist.

Test layering for this repo (mirrors the analytics/RS model; adapted because **this repo mutates**):
- **L1 (in almaapitk):** contract tests pin `get_collection_members` (GET, `total_record_count`), `add_to_collection` (POST `{"mms_id": ...}`), `remove_from_collection` (DELETE). Done upstream — not re-done here.
- **L2 (offline, this repo):** mock/golden test of the repo's **own** logic — `get_collection_count`, `get_collection_mms_ids` (offset pagination + `bib[].mms_id` extraction), and `update_collection_from_reports` (the add/remove **diff**: `to_add = report − collection`, `to_remove = collection − report`, dedup, empty-report skip-guard) — with the almaapitk boundary (`self.bibs`) and the Analytics fetch mocked. No network. This is what proves the bump didn't perturb this repo's behavior. *(To be added.)*
- **L3 (opt-in live, this repo):** a SANDBOX-only smoke that **adds** a synthetic test MMS to a SANDBOX collection, asserts membership/count went up, then **removes** it and asserts it went back — exercising all three methods, re-runnable. Gated behind `RUN_LIVE_SMOKE=1`, hard-pinned to `environment=="SANDBOX"`, never reads `ALMA_PROD_API_KEY`. Real SANDBOX collection/MMS values live in a **gitignored** data file (placeholders committed). *(To be added.)*

---

## (g) Verdict & recommendation

**Bumping `almaapitk` `>=0.3.1` → `>=0.4.6` is SAFE for this repo.** The three collection methods carrying the entire read/write path are byte-identical; every other symbol the repo imports/constructs/calls/reads/catches (`AlmaAPIClient(environment)`, `client.logger`, `client.base_url`, `client.api_key`, `AlmaAPIError.status_code`) is preserved with a compatible signature. The behavior deltas that reach this repo are improvements or no-ops: 0.4.6 adds retry resilience to the GET (read) and DELETE (remove) paths that 0.3.1 lacked, deliberately leaves the non-idempotent POST (add) un-retried, lowers the per-request timeout to a still-ample 60s, and quiets/redacts its own logging (which this repo overrides anyway).

**Recommended next steps (consumer-rollout gate):**
1. Add the L2 offline mock/golden test (§F) and the L3 opt-in SANDBOX add-then-remove smoke (§F), with the PROD-write refusal baked into L3.
2. Bump the pin in `pyproject.toml`: `almaapitk = ">=0.4.6"`.
3. `poetry update almaapitk` then `poetry run pytest` (offline). Run the L3 SANDBOX smoke manually with `RUN_LIVE_SMOKE=1` on the masedet box.
4. Re-verify on the masedet prod workstation per its own `poetry install` before fast-forward merging `main` → `prod`.
