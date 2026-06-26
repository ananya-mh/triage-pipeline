"""Tests for ingestion.py filter functions."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from log_triage.ingestion import prefilter, context_aware_filter


# --- prefilter tests ---

def test_removes_blank_lines():
    lines = ["line one", "", "   ", "line two"]
    result = prefilter(lines, profile="common")
    assert result == ["line one", "line two"]


def test_removes_linux_noise():
    lines = [
        "Jun 15 04:06:18 combo su(pam_unix)[21416]: session opened for user cyrus by (uid=0)",
        "Jun 15 04:06:19 combo su(pam_unix)[21416]: session closed for user cyrus",
        "Jun 15 12:12:34 combo sshd(pam_unix)[23397]: check pass; user unknown",
        "Jun 15 04:06:20 combo logrotate: ALERT exited abnormally with [1]",
        "Jun 17 07:07:00 combo ftpd[29504]: connection from 24.54.76.216 at Fri Jun 17 07:07:00 2005",
        "Jun 19 04:09:02 combo cups: cupsd startup succeeded",
        "Jun 19 04:09:11 combo syslogd 1.4.1: restart.",
    ]
    result = prefilter(lines, profile="linux")
    assert len(result) == 1
    assert "ALERT" in result[0]


def test_removes_hdfs_noise():
    lines = [
        "081109 203615 INFO dfs.DataNode$PacketResponder: PacketResponder 1 for block blk_123 terminating",
        "081109 203615 INFO dfs.DataNode$DataXceiver: Receiving block blk_456",
        "081109 203615 INFO dfs.FSNamesystem: BLOCK* NameSystem.allocateBlock: /user/root/file",
        "081109 203622 ERROR dfs.DataNode$DataXceiver: DataXceiver error: java.io.IOException",
    ]
    result = prefilter(lines, profile="hdfs")
    assert len(result) == 1
    assert "ERROR" in result[0]


def test_common_profile_keeps_linux_noise():
    lines = [
        "Jun 15 04:06:18 combo su(pam_unix)[21416]: session opened for user cyrus by (uid=0)",
        "Jun 15 04:06:20 combo logrotate: ALERT exited abnormally with [1]",
    ]
    result = prefilter(lines, profile="common")
    assert len(result) == 2


def test_removes_consecutive_dupes_by_normalized_form():
    lines = [
        "Jun 15 02:04:59 combo sshd(pam_unix)[20882]: authentication failure; rhost=1.2.3.4  user=root",
        "Jun 15 02:04:59 combo sshd(pam_unix)[20883]: authentication failure; rhost=1.2.3.4  user=root",
        "Jun 15 02:04:59 combo sshd(pam_unix)[20884]: authentication failure; rhost=1.2.3.4  user=root",
    ]
    result = prefilter(lines, profile="linux")
    assert len(result) == 1


def test_keeps_non_consecutive_dupes():
    lines = [
        "Jun 15 02:04:59 combo sshd(pam_unix)[20882]: authentication failure; rhost=1.2.3.4",
        "Jun 15 04:06:20 combo logrotate: ALERT exited abnormally with [1]",
        "Jun 16 02:04:59 combo sshd(pam_unix)[20999]: authentication failure; rhost=1.2.3.4",
    ]
    result = prefilter(lines, profile="linux")
    assert len(result) == 3


def test_empty_input():
    assert prefilter([], profile="linux") == []


def test_unknown_profile_uses_common_only():
    lines = [
        "",
        "heartbeat OK",
        "Jun 15 04:06:18 combo su(pam_unix)[21416]: session opened for user cyrus",
        "some real log line",
    ]
    result = prefilter(lines, profile="nonexistent")
    assert len(result) == 2
    assert "session opened" in result[0]
    assert "some real log line" in result[1]


# --- context_aware_filter tests ---

def test_keeps_context_around_priority_lines():
    lines = [
        "line 0 info",
        "line 1 info",
        "line 2 info",
        "line 3 authentication failure",
        "line 4 info",
        "line 5 info",
        "line 6 info",
        "line 7 info",
    ]
    result = context_aware_filter(lines, context=2)
    assert result == [
        "line 1 info",
        "line 2 info",
        "line 3 authentication failure",
        "line 4 info",
        "line 5 info",
    ]


def test_returns_all_lines_when_no_priority_found():
    lines = ["info line 1", "info line 2", "info line 3"]
    result = context_aware_filter(lines, context=3)
    assert result == lines


def test_empty_input_returns_empty():
    assert context_aware_filter([], context=3) == []


def test_priority_at_start():
    lines = [
        "fatal error occurred",
        "line 1",
        "line 2",
        "line 3",
        "line 4",
    ]
    result = context_aware_filter(lines, context=2)
    assert result == ["fatal error occurred", "line 1", "line 2"]


def test_priority_at_end():
    lines = [
        "line 0",
        "line 1",
        "line 2",
        "line 3",
        "connection timeout detected",
    ]
    result = context_aware_filter(lines, context=2)
    assert result == ["line 2", "line 3", "connection timeout detected"]


def test_overlapping_context_windows():
    lines = [
        "line 0",
        "error happened here",
        "line 2",
        "another failure here",
        "line 4",
    ]
    result = context_aware_filter(lines, context=1)
    assert result == lines


def test_context_zero_keeps_only_priority():
    lines = [
        "line 0",
        "line 1",
        "authentication failure detected",
        "line 3",
        "line 4",
    ]
    result = context_aware_filter(lines, context=0)
    assert result == ["authentication failure detected"]


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
