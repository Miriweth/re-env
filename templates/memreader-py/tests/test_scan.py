import pytest

from memreader.scan import find, find_all, parse_pattern


def test_parse_pattern():
    assert parse_pattern("48 8B ?? 05 ?") == [0x48, 0x8B, None, 0x05, None]


def test_parse_rejects_garbage():
    with pytest.raises(ValueError):
        parse_pattern("48 ZZ")


def test_find_with_wildcard():
    assert find(b"\x00\x48\x8b\x11\x05", parse_pattern("48 8B ?? 05")) == 1


def test_find_returns_none_when_absent():
    assert find(b"\x00\x01", parse_pattern("FF")) is None


def test_find_all():
    assert find_all(b"ABAB", parse_pattern("41 42")) == [0, 2]


def test_find_all_reports_overlapping_hits():
    assert find_all(b"AAA", parse_pattern("41 41")) == [0, 1]


def test_wildcard_matches_newline_and_high_bytes():
    assert find(b"\x01\n\xff\x02", parse_pattern("01 ?? ?? 02")) == 0
