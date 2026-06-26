"""Tests for detect_profile function."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from log_triage.ingestion import detect_profile


HDFS_LINES = [
    "081109 203615 148 INFO dfs.DataNode$PacketResponder: PacketResponder 1 for block blk_123 terminating",
    "081109 203615 149 INFO dfs.DataNode$DataXceiver: Receiving block blk_456",
    "081109 203615 150 INFO dfs.FSNamesystem: BLOCK* NameSystem.allocateBlock: /user/root/file",
    "081109 203622 ERROR dfs.DataNode$DataXceiver: DataXceiver error: java.io.IOException",
]

LINUX_LINES = [
    "Jun 14 15:16:01 combo sshd(pam_unix)[19939]: authentication failure; logname= uid=0 euid=0 tty=NODEVssh ruser= rhost=218.188.2.4",
    "Jun 15 04:06:18 combo su(pam_unix)[21416]: session opened for user cyrus by (uid=0)",
    "Jun 15 04:06:19 combo su(pam_unix)[21416]: session closed for user cyrus",
    "Jun 15 04:06:20 combo logrotate: ALERT exited abnormally with [1]",
]

GENERIC_LINES = [
    "2025-06-26 10:00:00 app started successfully",
    "2025-06-26 10:00:01 listening on port 8080",
    "2025-06-26 10:00:02 request received from 192.168.1.1",
    "2025-06-26 10:00:03 response sent in 42ms",
]


def test_detects_hdfs():
    assert detect_profile(HDFS_LINES) == "hdfs"


def test_detects_linux():
    assert detect_profile(LINUX_LINES) == "linux"


def test_defaults_to_common():
    assert detect_profile(GENERIC_LINES) == "common"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
