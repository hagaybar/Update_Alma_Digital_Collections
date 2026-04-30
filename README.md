# Update Alma Digital Collections

A small Python tool that keeps **Alma Digital Collections** in sync with one or more **Alma Analytics reports**. Point it at a collection ID and a list of report paths; it will compute the diff (items to add, items to remove) and apply it via the Alma APIs.

Built on top of [`almaapitk`](https://pypi.org/project/almaapitk/), a toolkit for working with the Ex Libris Alma APIs in Python.

---

## What it does

For each task in your config:

1. Pulls every MMS ID listed in the configured Analytics report(s).
2. Pulls the current members of the target digital collection.
3. Computes `to_add = report − collection` and `to_remove = collection − report`.
4. Calls `POST /bibs/collections/{id}/bibs` and `DELETE /bibs/collections/{id}/bibs/{mms_id}` to converge the collection on the report.

A dry-run mode (and a separate `dry_test.py` utility) reports the diff without touching Alma.

## Requirements

- Python **3.12+**
- An Alma API key with read access to **Bibs** and **Analytics**, and write access to **Bibs** for the collection you want to manage.
- Reports must return MMS IDs in the **first column** (`Column1` in the Analytics XML response).
- `almaapitk` currently targets the **EU Alma datacenter** (`api-eu.hosted.exlibrisgroup.com`). If you are on NA / APAC / CA / CN, you will need to fork or extend `almaapitk` to support your region.

## Installation

### With Poetry (recommended)

```bash
git clone https://github.com/hagaybar/Update_Alma_Digital_Collections.git
cd Update_Alma_Digital_Collections
poetry install
poetry shell
```

### With pip

```bash
git clone https://github.com/hagaybar/Update_Alma_Digital_Collections.git
cd Update_Alma_Digital_Collections
python -m venv .venv && source .venv/bin/activate
pip install "almaapitk>=0.3.1" "requests>=2.32" "beautifulsoup4>=4.12" "pyyaml>=6.0" lxml
```

## Configuration

### 1. API keys (environment variables)

`almaapitk` reads the API key from the environment, picking one based on the `environment` field in your config:

```bash
export ALMA_SB_API_KEY="your-sandbox-api-key"     # used when environment: SANDBOX
export ALMA_PROD_API_KEY="your-production-api-key" # used when environment: PRODUCTION
```

Add these to your shell profile, a `.env` you `source`, or your CI secret store. **Never commit them.**

### 2. `config.yml`

Copy the template and fill in your values:

```bash
cp config_sample.yml config.yml
```

```yaml
environment: SANDBOX  # or PRODUCTION

tasks:
  open_access_journals:
    collection_id: "81234567890001234"
    report_paths:
      - "/shared/My Institution/Reports/OA Journals - Active"

  thesis_collection:
    collection_id: "81234567890009999"
    report_paths:
      - "/shared/My Institution/Reports/Theses 2024"
      - "/shared/My Institution/Reports/Theses 2025"
```

Each task synchronizes one collection from the union of its `report_paths`. `config.yml` is gitignored — commit only `config_sample.yml`.

The tool resolves the config path in this order: `--config` flag → `ALMA_CONFIG_PATH` env var → `./config.yml` next to the script.

## Usage

### Run all tasks

```bash
python AlmaCollectionManager_6.py
```

### Run a specific task (or several)

```bash
python AlmaCollectionManager_6.py -t open_access_journals
python AlmaCollectionManager_6.py -t open_access_journals -t thesis_collection
```

### Dry run (no writes)

```bash
python AlmaCollectionManager_6.py --dry-run
```

### Use a non-default config

```bash
python AlmaCollectionManager_6.py --config /etc/alma/prod.yml
```

### Custom log directory

```bash
python AlmaCollectionManager_6.py --log-dir /var/log/alma-sync
```

### CLI flags

| Flag | Description |
| --- | --- |
| `-t, --task NAME` | Run a specific task (repeatable). Default: all tasks. |
| `-c, --config PATH` | Path to config file. Default: `./config.yml`. |
| `--dry-run` | Print what would happen; no API writes. |
| `--log-dir DIR` | Directory for timestamped log files. Default: `./logs`. |

## Previewing a diff with `dry_test.py`

`dry_test.py` is a more verbose preview tool that prints sample MMS IDs and counts before any change:

```bash
# Inline arguments
python dry_test.py --collection-id 81234567890001234 \
                   --report-path "/shared/My Institution/Reports/OA Journals - Active" \
                   --environment SANDBOX

# Or, drive it from your config
python dry_test.py --config config.yml --task open_access_journals
```

## Logging

Each run writes a timestamped log to `<log-dir>/alma_manager_YYYYMMDD_HHMMSS.log` and mirrors INFO+ output to the console. Log messages from `almaapitk`'s domain loggers (`almapi.api_client`, `almapi.bibs`, `almapi.admin`) are also captured in the archive file. `almaapitk` keeps its own per-domain DEBUG logs alongside.

## Project layout

```
.
├── AlmaCollectionManager_6.py   # main script (CLI entry point + sync logic)
├── dry_test.py                  # standalone preview utility
├── config_sample.yml            # template config (copy → config.yml)
├── pyproject.toml               # Poetry project, pins almaapitk >= 0.3.1
└── poetry.lock
```

## How the sync handles edge cases

- **Duplicate MMS IDs in reports** — deduplicated before any API call.
- **MMS already in the collection** (HTTP 400 "already assigned") — treated as success, logged at DEBUG.
- **Empty reports** — the run is skipped; the collection is not modified. This is intentional, to avoid accidentally clearing a collection because of a broken report.
- **Removal failures** (e.g. the bib has representations attached) — logged as warnings; the run continues.
- **Analytics pagination** — handled via the `ResumptionToken` / `IsFinished` markers; default page size 100.

## Related

- [`almaapitk`](https://pypi.org/project/almaapitk/) — the underlying Python toolkit for Alma APIs (Bibs, Acquisitions, Resource Sharing, Users, Admin, Digital Representations). [Source](https://github.com/hagaybar/AlmaAPITK).
- [Ex Libris Alma APIs](https://developers.exlibrisgroup.com/alma/apis/) — official API reference.

## Author

Hagay Bar — Tel Aviv University Libraries.
