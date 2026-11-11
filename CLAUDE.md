# CLAUDE.md

Syncs Alma digital collection membership to an Analytics report (`collection_sync.py`). It is a
scheduled, unattended production job on masedet that writes to Alma. See `README.md` for usage.

## almaapitk bumps

Any change to the `almaapitk` pin follows `docs/almaapitk-bump-protocol.md` (binding): one bump
at a time, from this repo, with an audit in `docs/almaapitk-<version>-audit.md`.
