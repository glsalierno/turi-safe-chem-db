"""Unit tests for PubChem throttling, rate limiting, and caching.

These tests use mocked HTTP responses — no live PubChem calls.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from unittest import mock

import pytest
import requests

from packages.doss_core.pubchem import (
    PubChemError,
    PubChemNotFoundError,
    PubChemThrottledError,
    _compute_delay,
    _get_cache_dir,
    _get_retry_after,
    _get_with_retries,
    _is_throttle_response,
    _read_cache,
    _throttle,
    _write_cache,
    clear_cache,
    get_cache_stats,
    get_cid_by_cas,
    get_compound_properties,
)


@pytest.fixture
def temp_cache_dir(monkeypatch):
    """Create a temporary cache directory for tests."""
    tmpdir = tempfile.mkdtemp(prefix="pubchem_test_cache_")
    monkeypatch.setenv("PUBCHEM_CACHE_DIR", tmpdir)
    import packages.doss_core.pubchem as pc
    pc._CACHE_DIR = None
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def fast_intervals(monkeypatch):
    """Speed up tests by reducing intervals."""
    monkeypatch.setenv("PUBCHEM_MIN_INTERVAL_S", "0.01")
    monkeypatch.setenv("PUBCHEM_MAX_RETRIES", "3")
    import packages.doss_core.pubchem as pc
    pc._MIN_INTERVAL_S = 0.01
    pc._MAX_RETRIES = 3
    pc._BASE_DELAY = 0.01
    pc._MAX_DELAY = 0.1
    yield


class TestThrottleDetection:
    """Test throttle response detection."""

    def test_503_is_throttle(self):
        resp = mock.Mock()
        resp.status_code = 503
        resp.text = ""
        assert _is_throttle_response(resp) is True

    def test_429_is_throttle(self):
        resp = mock.Mock()
        resp.status_code = 429
        resp.text = ""
        assert _is_throttle_response(resp) is True

    def test_serverbusy_text_is_throttle(self):
        resp = mock.Mock()
        resp.status_code = 200
        resp.text = "PUGREST.ServerBusy"
        assert _is_throttle_response(resp) is True

    def test_too_many_requests_text_is_throttle(self):
        resp = mock.Mock()
        resp.status_code = 200
        resp.text = "Too many requests from your IP"
        assert _is_throttle_response(resp) is True

    def test_200_ok_not_throttle(self):
        resp = mock.Mock()
        resp.status_code = 200
        resp.text = '{"IdentifierList": {"CID": [123]}}'
        assert _is_throttle_response(resp) is False


class TestRetryAfterHeader:
    """Test Retry-After header parsing."""

    def test_numeric_retry_after(self):
        resp = mock.Mock()
        resp.headers = {"Retry-After": "30"}
        assert _get_retry_after(resp) == 30.0

    def test_float_retry_after(self):
        resp = mock.Mock()
        resp.headers = {"Retry-After": "15.5"}
        assert _get_retry_after(resp) == 15.5

    def test_missing_retry_after(self):
        resp = mock.Mock()
        resp.headers = {}
        assert _get_retry_after(resp) is None

    def test_invalid_retry_after(self):
        resp = mock.Mock()
        resp.headers = {"Retry-After": "not-a-number"}
        assert _get_retry_after(resp) is None


class TestBackoffDelay:
    """Test exponential backoff with jitter."""

    def test_delay_increases_with_attempts(self):
        d0 = _compute_delay(0)
        d1 = _compute_delay(1)
        d2 = _compute_delay(2)
        assert d1 > d0 * 1.5
        assert d2 > d1 * 1.5

    def test_delay_respects_retry_after(self):
        delay = _compute_delay(0, retry_after=30.0)
        assert delay >= 30.0

    def test_delay_has_jitter(self):
        delays = [_compute_delay(1) for _ in range(20)]
        assert len(set(delays)) > 1


class TestRateLimiting:
    """Test process-wide rate limiting."""

    def test_throttle_enforces_interval(self, monkeypatch):
        monkeypatch.setenv("PUBCHEM_MIN_INTERVAL_S", "0.1")
        import packages.doss_core.pubchem as pc
        pc._MIN_INTERVAL_S = 0.1
        pc._last_request_at = time.monotonic()

        start = time.monotonic()
        _throttle()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.05


class TestCache:
    """Test disk caching."""

    def test_write_and_read_cache(self, temp_cache_dir):
        url = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/67-64-1/cids/JSON"
        data = {"IdentifierList": {"CID": [180]}}

        _write_cache(url, data)
        cached = _read_cache(url)
        assert cached == data

    def test_cache_miss_returns_none(self, temp_cache_dir):
        url = "https://nonexistent.example.com/test"
        assert _read_cache(url) is None

    def test_cache_stats(self, temp_cache_dir):
        url = "https://example.com/test"
        _write_cache(url, {"test": True})

        stats = get_cache_stats()
        assert stats["file_count"] == 1
        assert stats["total_size_bytes"] > 0
        assert temp_cache_dir in stats["cache_dir"]

    def test_clear_cache(self, temp_cache_dir):
        _write_cache("https://a.com", {"a": 1})
        _write_cache("https://b.com", {"b": 2})

        count = clear_cache()
        assert count == 2

        stats = get_cache_stats()
        assert stats["file_count"] == 0


class TestGetWithRetries:
    """Test the main retry function with mocked HTTP."""

    def test_success_on_first_try(self, temp_cache_dir, fast_intervals):
        mock_resp = mock.Mock()
        mock_resp.status_code = 200
        mock_resp.headers = {}
        mock_resp.json.return_value = {"IdentifierList": {"CID": [180]}}
        mock_resp.raise_for_status = mock.Mock()

        with mock.patch("requests.get", return_value=mock_resp):
            resp = _get_with_retries(
                "https://pubchem.ncbi.nlm.nih.gov/test",
                label="test",
                use_cache=False,
            )
            assert resp.status_code == 200

    def test_retry_on_503_then_success(self, temp_cache_dir, fast_intervals):
        mock_503 = mock.Mock()
        mock_503.status_code = 503
        mock_503.headers = {}
        mock_503.text = "PUGREST.ServerBusy"

        mock_200 = mock.Mock()
        mock_200.status_code = 200
        mock_200.headers = {}
        mock_200.json.return_value = {"test": True}
        mock_200.raise_for_status = mock.Mock()

        with mock.patch("requests.get", side_effect=[mock_503, mock_200]):
            resp = _get_with_retries(
                "https://pubchem.ncbi.nlm.nih.gov/test",
                label="test",
                use_cache=False,
            )
            assert resp.status_code == 200

    def test_throttled_error_after_retries_exhausted(self, temp_cache_dir, fast_intervals):
        mock_503 = mock.Mock()
        mock_503.status_code = 503
        mock_503.headers = {"Retry-After": "60"}
        mock_503.text = "PUGREST.ServerBusy"

        with mock.patch("requests.get", return_value=mock_503):
            with pytest.raises(PubChemThrottledError) as exc_info:
                _get_with_retries(
                    "https://pubchem.ncbi.nlm.nih.gov/test",
                    label="test",
                    attempts=2,
                    use_cache=False,
                )
            assert "throttled" in str(exc_info.value).lower()
            assert exc_info.value.retry_after == 60.0

    def test_404_raises_not_found(self, temp_cache_dir, fast_intervals):
        mock_404 = mock.Mock()
        mock_404.status_code = 404
        mock_404.headers = {}
        mock_404.text = "Not found"

        with mock.patch("requests.get", return_value=mock_404):
            with pytest.raises(PubChemNotFoundError):
                _get_with_retries(
                    "https://pubchem.ncbi.nlm.nih.gov/test",
                    label="test",
                    use_cache=False,
                )

    def test_cache_hit_skips_network(self, temp_cache_dir, fast_intervals):
        url = "https://pubchem.ncbi.nlm.nih.gov/test"
        cached_data = {"cached": True}
        _write_cache(url, cached_data)

        with mock.patch("requests.get") as mock_get:
            resp = _get_with_retries(url, label="test", use_cache=True)
            mock_get.assert_not_called()
            assert resp.headers.get("X-Cache") == "HIT"
            assert resp.json() == cached_data

    def test_429_triggers_retry(self, temp_cache_dir, fast_intervals):
        mock_429 = mock.Mock()
        mock_429.status_code = 429
        mock_429.headers = {"Retry-After": "5"}
        mock_429.text = "Too many requests"

        mock_200 = mock.Mock()
        mock_200.status_code = 200
        mock_200.headers = {}
        mock_200.json.return_value = {"success": True}
        mock_200.raise_for_status = mock.Mock()

        with mock.patch("requests.get", side_effect=[mock_429, mock_200]):
            resp = _get_with_retries(
                "https://pubchem.ncbi.nlm.nih.gov/test",
                label="test",
                use_cache=False,
            )
            assert resp.status_code == 200


class TestGetCidByCas:
    """Test CID lookup by CAS."""

    def test_cid_found(self, temp_cache_dir, fast_intervals):
        mock_resp = mock.Mock()
        mock_resp.status_code = 200
        mock_resp.headers = {}
        mock_resp.json.return_value = {"IdentifierList": {"CID": [180]}}
        mock_resp.raise_for_status = mock.Mock()

        with mock.patch("requests.get", return_value=mock_resp):
            cid = get_cid_by_cas("67-64-1")
            assert cid == 180

    def test_cid_not_found_returns_none(self, temp_cache_dir, fast_intervals):
        mock_404 = mock.Mock()
        mock_404.status_code = 404
        mock_404.headers = {}
        mock_404.text = "Not found"

        with mock.patch("requests.get", return_value=mock_404):
            cid = get_cid_by_cas("99999-99-9")
            assert cid is None

    def test_throttle_propagates(self, temp_cache_dir, fast_intervals):
        mock_503 = mock.Mock()
        mock_503.status_code = 503
        mock_503.headers = {}
        mock_503.text = "PUGREST.ServerBusy"

        with mock.patch("requests.get", return_value=mock_503):
            with pytest.raises(PubChemThrottledError):
                get_cid_by_cas("67-64-1")


class TestGetCompoundProperties:
    """Test compound property fetching."""

    def test_properties_success(self, temp_cache_dir, fast_intervals):
        mock_resp = mock.Mock()
        mock_resp.status_code = 200
        mock_resp.headers = {}
        mock_resp.json.return_value = {
            "PropertyTable": {
                "Properties": [
                    {
                        "CID": 180,
                        "MolecularFormula": "C3H6O",
                        "MolecularWeight": 58.08,
                        "CanonicalSMILES": "CC(=O)C",
                    }
                ]
            }
        }
        mock_resp.raise_for_status = mock.Mock()

        with mock.patch("requests.get", return_value=mock_resp):
            props = get_compound_properties(180)
            assert props["MolecularFormula"] == "C3H6O"
            assert props["MolecularWeight"] == 58.08
            assert props["CanonicalSMILES"] == "CC(=O)C"


class TestExceptionTypes:
    """Test exception class hierarchy."""

    def test_throttled_is_pubchem_error(self):
        exc = PubChemThrottledError("test", retry_after=30)
        assert isinstance(exc, PubChemError)
        assert exc.retry_after == 30

    def test_not_found_is_pubchem_error(self):
        exc = PubChemNotFoundError("test")
        assert isinstance(exc, PubChemError)


class TestEnvConfigurable:
    """Test environment variable configuration."""

    def test_min_interval_from_env(self, monkeypatch):
        monkeypatch.setenv("PUBCHEM_MIN_INTERVAL_S", "2.5")
        import importlib
        import packages.doss_core.pubchem as pc
        importlib.reload(pc)
        assert pc._MIN_INTERVAL_S == 2.5

    def test_max_retries_from_env(self, monkeypatch):
        monkeypatch.setenv("PUBCHEM_MAX_RETRIES", "10")
        import importlib
        import packages.doss_core.pubchem as pc
        importlib.reload(pc)
        assert pc._MAX_RETRIES == 10

    def test_cache_dir_from_env(self, monkeypatch, tmp_path):
        custom_dir = tmp_path / "custom_cache"
        monkeypatch.setenv("PUBCHEM_CACHE_DIR", str(custom_dir))
        import packages.doss_core.pubchem as pc
        pc._CACHE_DIR = None

        cache_dir = _get_cache_dir()
        assert str(cache_dir) == str(custom_dir)
        assert cache_dir.exists()
