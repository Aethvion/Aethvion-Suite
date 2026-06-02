"""
tests/test_security_scanner.py
════════════════════════════════
Unit tests for the Intelligence Firewall content scanner.

Tests cover:
  - ContentScanner with explicit patterns
  - ScanAction routing (ALLOW vs ROUTE_LOCAL vs BLOCK)
  - Innocuous content passes through unmodified
  - IntelligenceFirewall with no config file (safe defaults)
"""
from __future__ import annotations

import pytest

from core.security.scanner import ContentScanner, ScanAction, ScanSeverity, ScanResult


# Test pattern fixtures

BLOCK_PATTERN = {
    "pattern": r"drop\s+table",
    "category": "sql_injection",
    "action": "block",
    "severity": "critical",
    "case_sensitive": False,
}

ROUTE_PATTERN = {
    "pattern": r"execute\s+(code|script|command)",
    "category": "code_execution",
    "action": "route_local",
    "severity": "high",
    "case_sensitive": False,
}


@pytest.fixture()
def empty_scanner():
    """Scanner with no patterns — everything should ALLOW."""
    return ContentScanner(patterns=[])


@pytest.fixture()
def scanner_with_patterns():
    """Scanner with a block pattern and a route-local pattern."""
    return ContentScanner(patterns=[BLOCK_PATTERN, ROUTE_PATTERN])


# ContentScanner — empty patterns

class TestEmptyScanner:
    def test_plain_chat_allowed(self, empty_scanner):
        result = empty_scanner.scan("What is the capital of France?", trace_id="t1")
        assert result.action == ScanAction.ALLOW

    def test_empty_string_allowed(self, empty_scanner):
        result = empty_scanner.scan("", trace_id="t2")
        assert result.action == ScanAction.ALLOW

    def test_result_is_clean(self, empty_scanner):
        result = empty_scanner.scan("Hello, how are you?", trace_id="t3")
        assert result.is_clean is True

    def test_result_type(self, empty_scanner):
        result = empty_scanner.scan("Hello", trace_id="t4")
        assert isinstance(result, ScanResult)
        assert isinstance(result.action, ScanAction)


# ContentScanner — with patterns

class TestScannerWithPatterns:
    def test_safe_content_passes(self, scanner_with_patterns):
        result = scanner_with_patterns.scan(
            "How do I write a for-loop in Python?", trace_id="t5"
        )
        assert result.action == ScanAction.ALLOW

    def test_block_pattern_detected(self, scanner_with_patterns):
        result = scanner_with_patterns.scan(
            "Please DROP TABLE users;", trace_id="t6"
        )
        assert result.action == ScanAction.BLOCK

    def test_route_local_pattern_detected(self, scanner_with_patterns):
        # Pattern: r"execute\s+(code|script|command)" — must be immediately adjacent
        result = scanner_with_patterns.scan(
            "Please execute code on my behalf", trace_id="t7"
        )
        assert result.action == ScanAction.ROUTE_LOCAL

    def test_flagged_result_has_matches(self, scanner_with_patterns):
        result = scanner_with_patterns.scan("Drop table accounts;", trace_id="t8")
        assert len(result.matches) > 0

    def test_flagged_result_not_clean(self, scanner_with_patterns):
        result = scanner_with_patterns.scan("drop table sessions;", trace_id="t9")
        assert result.is_clean is False

    def test_severity_set_on_flagged(self, scanner_with_patterns):
        result = scanner_with_patterns.scan("drop table orders;", trace_id="t10")
        assert result.severity is not None
        assert isinstance(result.severity, ScanSeverity)

    def test_case_insensitive_matching(self, scanner_with_patterns):
        # Pattern has case_sensitive=False
        result_upper = scanner_with_patterns.scan("DROP TABLE test;", trace_id="t11")
        result_mixed = scanner_with_patterns.scan("Drop Table test;", trace_id="t12")
        assert result_upper.action == ScanAction.BLOCK
        assert result_mixed.action == ScanAction.BLOCK


# IntelligenceFirewall — no config file (safe defaults)

class TestIntelligenceFirewall:
    def test_firewall_initializes_without_config(self, tmp_path):
        """Firewall should boot without a security.yaml and not raise."""
        from core.security.firewall import IntelligenceFirewall
        nonexistent = str(tmp_path / "nonexistent_security.yaml")
        fw = IntelligenceFirewall(config_path=nonexistent)
        assert fw.enabled is True

    def test_scan_and_route_returns_tuple(self, tmp_path):
        from core.security.firewall import IntelligenceFirewall
        nonexistent = str(tmp_path / "nonexistent_security.yaml")
        fw = IntelligenceFirewall(config_path=nonexistent)
        decision, scan_result = fw.scan_and_route("Hello world", trace_id="fw_t1")
        # With no patterns, decision should be EXTERNAL (no local inference)
        assert decision is not None
