import json
from pathlib import Path

from tender_extractor.extraction.report import REPORT_FILE, find_multipage_tables, generate_report


def table(page, cols, rows=5, first_row=("a", "b")):
    return {"pages": [page], "num_rows": rows, "num_cols": cols, "first_row": list(first_row)}


def test_consecutive_pages_same_columns_are_candidates():
    found = find_multipage_tables([table(3, 4), table(4, 4)])
    assert found == [{"pages": [3, 4], "num_cols": 4, "repeated_header": True}]


def test_different_columns_or_gap_are_not_candidates():
    assert find_multipage_tables([table(3, 4), table(4, 5)]) == []
    assert find_multipage_tables([table(3, 4), table(5, 4)]) == []


def test_empty_tables_are_ignored():
    assert find_multipage_tables([table(3, 4, rows=0), table(4, 4, rows=0)]) == []


def test_different_first_row_is_not_a_repeated_header():
    found = find_multipage_tables([table(3, 4, first_row=("a", "b")), table(4, 4, first_row=("x", "y"))])
    assert found[0]["repeated_header"] is False


def test_unordered_tables_are_sorted_by_page():
    found = find_multipage_tables([table(4, 4), table(3, 4)])
    assert found[0]["pages"] == [3, 4]


def segment(status, errors=(), tables=()):
    return {"status": status, "errors": list(errors), "tables": list(tables)}


def test_status_success_when_all_segments_succeed(tmp_path):
    report = generate_report(tmp_path, Path("a.pdf"), [segment("success"), segment("success")], 1.0)
    assert report["status"] == "success"


def test_status_partial_when_some_segments_fail(tmp_path):
    report = generate_report(tmp_path, Path("a.pdf"), [segment("success"), segment("failure")], 1.0)
    assert report["status"] == "partial_success"


def test_status_failure_without_segments_keeps_extra_errors(tmp_path):
    error = {"component": "pdf-reader", "message": "boom"}
    report = generate_report(tmp_path, Path("a.pdf"), [], 1.0, errors=[error])
    assert report["status"] == "failure"
    assert report["errors"] == [error]


def test_report_is_written_and_includes_segment_errors(tmp_path):
    error = {"component": "ocr", "message": "bad page"}
    report = generate_report(tmp_path, Path("a.pdf"), [segment("failure", errors=[error])], 2.34)
    assert json.loads((tmp_path / REPORT_FILE).read_text(encoding="utf-8")) == report
    assert report["errors"] == [error]
    assert report["seconds"] == 2.3


def test_multipage_tables_are_collected_across_segments(tmp_path):
    segments = [segment("success", tables=[table(3, 4)]), segment("success", tables=[table(4, 4)])]
    report = generate_report(tmp_path, Path("a.pdf"), segments, 1.0)
    assert len(report["multipage_tables"]) == 1
