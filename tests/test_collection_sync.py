"""Unit tests for the diff and safety-guard logic in collection_sync."""

import logging

import pytest

from almaapitk import AlmaAPIError
from collection_sync import (
    AlmaCollectionManager,
    ReportError,
    SyncPlan,
    extract_mms_ids,
    plan_sync,
)


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class FakeBibs:
    """In-memory stand-in for almaapitk.BibliographicRecords collection methods."""

    def __init__(self, members, fail_add=(), already_assigned=()):
        self.members = list(members)
        self.added = []
        self.removed = []
        self.fail_add = set(fail_add)
        self.already_assigned = set(already_assigned)

    def get_collection_members(self, collection_id, limit=100, offset=0):
        page = self.members[offset:offset + limit]
        return FakeResponse({
            "total_record_count": len(self.members),
            "bib": [{"mms_id": m} for m in page],
        })

    def add_to_collection(self, collection_id, mms_id):
        if mms_id in self.already_assigned:
            raise AlmaAPIError("Bib is already assigned to collection", status_code=400)
        if mms_id in self.fail_add:
            raise AlmaAPIError("boom", status_code=500)
        self.added.append(mms_id)

    def remove_from_collection(self, collection_id, mms_id):
        self.removed.append(mms_id)


class FakeAnalytics:
    """Maps report path → rows, or → exception to raise."""

    def __init__(self, reports):
        self.reports = reports

    def fetch_report_rows(self, report_path):
        result = self.reports[report_path]
        if isinstance(result, Exception):
            raise result
        return result


class FakeClient:
    logger = logging.getLogger("test")


def rows(*mms_ids):
    return [{"Column0": "0", "Column1": m} for m in mms_ids]


def make_manager(members, reports, **bibs_kwargs):
    bibs = FakeBibs(members, **bibs_kwargs)
    manager = AlmaCollectionManager(
        FakeClient(), "COLL", bibs=bibs, analytics=FakeAnalytics(reports)
    )
    return manager, bibs


# --- plan_sync ---------------------------------------------------------------

def test_plan_add_and_remove_sets():
    plan = plan_sync(["1", "2", "3"], ["2", "3", "4"])
    assert plan == SyncPlan(to_add=["1"], to_remove=["4"])


def test_plan_deduplicates_report_ids():
    plan = plan_sync(["1", "1", "2"], [])
    assert plan.to_add == ["1", "2"]


def test_plan_empty_report_removes_nothing():
    assert plan_sync([], ["1", "2"]) == SyncPlan()


def test_plan_no_change_when_in_sync():
    assert plan_sync(["1", "2"], ["2", "1"]) == SyncPlan()


# --- extract_mms_ids ---------------------------------------------------------

def test_extract_skips_blank_values():
    assert extract_mms_ids(rows("1", " ", "2 "), "/r") == ["1", "2"]


@pytest.mark.parametrize("report_rows", [
    [],                                   # no rows
    [{"Column0": "0"}],                   # MMS ID column missing
    rows("1") + [{"Column0": "0"}],       # some rows missing it
    rows("", "  "),                       # only blanks
])
def test_extract_rejects_empty_or_malformed(report_rows):
    with pytest.raises(ReportError):
        extract_mms_ids(report_rows, "/r")


# --- update_collection_from_reports ------------------------------------------

def test_sync_adds_and_removes():
    manager, bibs = make_manager(["2", "4"], {"/a": rows("1", "2"), "/b": rows("3")})
    plan = manager.update_collection_from_reports(["/a", "/b"])
    assert plan == SyncPlan(to_add=["1", "3"], to_remove=["4"])
    assert bibs.added == ["1", "3"]
    assert bibs.removed == ["4"]


def test_empty_report_changes_nothing():
    manager, bibs = make_manager(["1", "2"], {"/a": []})
    assert manager.update_collection_from_reports(["/a"]) is None
    assert bibs.added == [] and bibs.removed == []


def test_one_empty_report_among_several_changes_nothing():
    # Without the guard, items only in /b would be removed.
    manager, bibs = make_manager(["1", "2"], {"/a": rows("1"), "/b": []})
    assert manager.update_collection_from_reports(["/a", "/b"]) is None
    assert bibs.added == [] and bibs.removed == []


def test_malformed_report_changes_nothing():
    manager, bibs = make_manager(["1", "2"], {"/a": [{"Column0": "0", "Column2": "x"}]})
    assert manager.update_collection_from_reports(["/a"]) is None
    assert bibs.removed == []


def test_failed_report_raises_before_any_write():
    manager, bibs = make_manager(
        ["1", "2"], {"/a": rows("1"), "/b": AlmaAPIError("down", status_code=500)}
    )
    with pytest.raises(AlmaAPIError):
        manager.update_collection_from_reports(["/a", "/b"])
    assert bibs.added == [] and bibs.removed == []


def test_no_report_paths_changes_nothing():
    manager, bibs = make_manager(["1"], {})
    assert manager.update_collection_from_reports([]) is None
    assert bibs.removed == []


# --- collection reads and writes ---------------------------------------------

def test_collection_members_paginate():
    members = [str(i) for i in range(250)]
    manager, _ = make_manager(members, {})
    assert manager.get_collection_mms_ids() == members


def test_add_tolerates_already_assigned_and_continues_after_errors(caplog):
    manager, bibs = make_manager([], {}, fail_add={"2"}, already_assigned={"1"})
    with caplog.at_level(logging.INFO, logger="test"):
        manager.add_to_collection(["1", "2", "3"])
    assert bibs.added == ["3"]
    assert "Success: 2, Errors: 1" in caplog.text
