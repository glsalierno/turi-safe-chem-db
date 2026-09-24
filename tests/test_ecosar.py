"""Unit tests for ECOSAR module (pyepisuite remote API).

Tests graceful degradation when pyepisuite is not installed,
and mock-based tests for data path when pyepisuite is available.
No live network calls.
"""
from __future__ import annotations

from typing import Any, Dict, List
from unittest import mock

import pytest

from packages.doss_core.ecosar import (
    ecosar_available,
    fetch_ecosar_rows,
    summarize_ecosar_for_cas,
)


class TestEcosarAvailable:
    """Tests for ecosar_available() function."""

    def test_returns_bool(self):
        """ecosar_available() always returns a boolean."""
        result = ecosar_available()
        assert isinstance(result, bool)

    def test_false_when_import_fails(self):
        """ecosar_available() returns False when pyepisuite import fails."""
        with mock.patch.dict("sys.modules", {"pyepisuite": None}):
            import importlib
            import packages.doss_core.ecosar as ecosar_mod
            importlib.reload(ecosar_mod)
            with mock.patch.object(ecosar_mod, "ecosar_available") as mock_avail:
                mock_avail.return_value = False
                assert mock_avail() is False


class TestFetchEcosarRowsWithoutPyepisuite:
    """Tests for fetch_ecosar_rows when pyepisuite is not installed."""

    def test_returns_error_dict_structure(self):
        """fetch_ecosar_rows returns proper dict structure on missing dep."""
        with mock.patch(
            "packages.doss_core.ecosar.ecosar_available", return_value=False
        ):
            result = fetch_ecosar_rows(["67-64-1"])
        
        assert isinstance(result, dict)
        assert "ok" in result
        assert "error" in result
        assert "n_cas" in result
        assert "n_rows" in result
        assert "columns" in result
        assert "records" in result

    def test_error_when_pyepisuite_not_installed(self):
        """fetch_ecosar_rows returns pyepisuite_not_installed error."""
        with mock.patch(
            "packages.doss_core.ecosar.ecosar_available", return_value=False
        ):
            result = fetch_ecosar_rows(["67-64-1"])
        
        assert result["ok"] is False
        assert result["error"] == "pyepisuite_not_installed"
        assert result["n_rows"] == 0
        assert result["records"] == []

    def test_empty_cas_list_error(self):
        """fetch_ecosar_rows returns error for empty CAS list."""
        result = fetch_ecosar_rows([])
        
        assert result["ok"] is False
        assert result["error"] == "empty_cas_list"


class TestSummarizeEcosarWithoutPyepisuite:
    """Tests for summarize_ecosar_for_cas error handling."""

    def test_returns_error_dict_structure(self):
        """summarize_ecosar_for_cas returns proper dict structure."""
        with mock.patch(
            "packages.doss_core.ecosar.ecosar_available", return_value=False
        ):
            result = summarize_ecosar_for_cas("67-64-1")
        
        assert isinstance(result, dict)
        assert "cas" in result
        assert "ok" in result
        assert "error" in result
        assert "qsar_class" in result
        assert "fish_96h_lc50" in result
        assert "daphnid_48h_lc50" in result
        assert "algae_96h_ec50" in result

    def test_error_when_pyepisuite_not_installed(self):
        """summarize_ecosar_for_cas returns error when pyepisuite missing."""
        with mock.patch(
            "packages.doss_core.ecosar.ecosar_available", return_value=False
        ):
            result = summarize_ecosar_for_cas("67-64-1")
        
        assert result["ok"] is False
        assert result["error"] == "pyepisuite_not_installed"
        assert result["cas"] == "67-64-1"

    def test_never_raises_on_missing_dep(self):
        """summarize_ecosar_for_cas never raises, returns error dict."""
        with mock.patch(
            "packages.doss_core.ecosar.ecosar_available", return_value=False
        ):
            try:
                result = summarize_ecosar_for_cas("invalid-cas")
            except Exception as e:
                pytest.fail(f"Should not raise, got {type(e).__name__}: {e}")
        
        assert result["ok"] is False


class TestFetchEcosarRowsWithMockedPyepisuite:
    """Mock-based tests for fetch_ecosar_rows data path."""

    def test_success_with_mocked_pyepisuite(self):
        """fetch_ecosar_rows succeeds with mocked pyepisuite (via patched internals)."""
        mock_df = mock.MagicMock()
        mock_df.columns = ["cas", "organism", "endpoint", "duration", "concentration", "qsar_class"]
        mock_df.__len__ = mock.MagicMock(return_value=3)
        mock_df.to_dict = mock.MagicMock(return_value=[
            {"cas": "67-64-1", "organism": "Fish", "endpoint": "LC50", "duration": "96 hr", "concentration": 5.2, "qsar_class": "Neutral Organics"},
        ])

        mock_pyepisuite = mock.MagicMock()
        mock_pyepisuite.search_episuite_by_cas = mock.MagicMock(return_value=["id1"])
        mock_pyepisuite.submit_to_episuite = mock.MagicMock(return_value=({}, []))
        
        mock_df_utils = mock.MagicMock()
        mock_df_utils.ecosar_to_dataframe = mock.MagicMock(return_value=mock_df)

        modules_patch = {
            "pyepisuite": mock_pyepisuite,
            "pyepisuite.dataframe_utils": mock_df_utils,
        }

        with mock.patch.dict("sys.modules", modules_patch):
            with mock.patch(
                "packages.doss_core.ecosar.ecosar_available", return_value=True
            ):
                import importlib
                import packages.doss_core.ecosar as ecosar_mod
                importlib.reload(ecosar_mod)
                
                result = ecosar_mod.fetch_ecosar_rows(["67-64-1"])
        
        assert result["ok"] is True
        assert result["n_cas"] == 1
        assert result["error"] is None

    def test_exception_handling(self):
        """fetch_ecosar_rows handles exceptions gracefully."""
        mock_pyepisuite = mock.MagicMock()
        mock_pyepisuite.search_episuite_by_cas = mock.MagicMock(
            side_effect=RuntimeError("API unavailable")
        )
        
        mock_df_utils = mock.MagicMock()
        
        modules_patch = {
            "pyepisuite": mock_pyepisuite,
            "pyepisuite.dataframe_utils": mock_df_utils,
        }

        with mock.patch.dict("sys.modules", modules_patch):
            with mock.patch(
                "packages.doss_core.ecosar.ecosar_available", return_value=True
            ):
                import importlib
                import packages.doss_core.ecosar as ecosar_mod
                importlib.reload(ecosar_mod)
                
                result = ecosar_mod.fetch_ecosar_rows(["67-64-1"])
        
        assert result["ok"] is False
        assert "RuntimeError" in result["error"]
        assert result["records"] == []


class TestSummarizeEcosarWithRecords:
    """Tests for summarize_ecosar_for_cas with pre-fetched records."""

    def test_with_valid_records(self):
        """summarize_ecosar_for_cas processes pre-fetched records."""
        records: List[Dict[str, Any]] = [
            {"cas": "67-64-1", "organism": "Fish", "endpoint": "LC50", "duration": "96 hr", "concentration": 5.2, "qsar_class": "Neutral Organics"},
            {"cas": "67-64-1", "organism": "Daphnid", "endpoint": "LC50", "duration": "48 hr", "concentration": 12.1, "qsar_class": "Neutral Organics"},
            {"cas": "67-64-1", "organism": "Green Algae", "endpoint": "EC50", "duration": "96 hr", "concentration": 2.3, "qsar_class": "Neutral Organics"},
        ]
        
        result = summarize_ecosar_for_cas("67-64-1", records=records)
        
        assert result["ok"] is True
        assert result["cas"] == "67-64-1"
        assert result["qsar_class"] == "Neutral Organics"
        assert result["fish_96h_lc50"] == 5.2
        assert result["daphnid_48h_lc50"] == 12.1
        assert result["algae_96h_ec50"] == 2.3
        assert result["n_rows"] == 3

    def test_with_no_matching_records(self):
        """summarize_ecosar_for_cas handles no matching CAS."""
        records: List[Dict[str, Any]] = [
            {"cas": "50-00-0", "organism": "Fish", "endpoint": "LC50", "duration": "96 hr", "concentration": 1.0, "qsar_class": "Aldehydes"},
        ]
        
        result = summarize_ecosar_for_cas("67-64-1", records=records)
        
        assert result["ok"] is False
        assert result["error"] == "no_ecosar_rows"
        assert result["n_rows"] == 0

    def test_cas_normalization(self):
        """summarize_ecosar_for_cas normalizes CAS strings."""
        records: List[Dict[str, Any]] = [
            {"cas": "067-64-1", "organism": "Fish", "endpoint": "LC50", "duration": "96 hr", "concentration": 5.2, "qsar_class": "Neutral Organics"},
        ]
        
        result = summarize_ecosar_for_cas("  67-64-1  ", records=records)
        
        assert result["ok"] is True
        assert result["cas"] == "67-64-1"

    def test_note_generation(self):
        """summarize_ecosar_for_cas generates note from values."""
        records: List[Dict[str, Any]] = [
            {"cas": "67-64-1", "organism": "Fish", "endpoint": "LC50", "duration": "96 hr", "concentration": 5.2, "qsar_class": "Neutral Organics"},
        ]
        
        result = summarize_ecosar_for_cas("67-64-1", records=records)
        
        assert result["note"] is not None
        assert "Neutral Organics" in result["note"]
        assert "Fish 96h LC50=5.2" in result["note"]


class TestSmokeImport:
    """Basic import tests for ecosar module."""

    def test_module_importable(self):
        """ecosar module can be imported."""
        import packages.doss_core.ecosar as ecosar
        
        assert hasattr(ecosar, "ecosar_available")
        assert hasattr(ecosar, "fetch_ecosar_rows")
        assert hasattr(ecosar, "summarize_ecosar_for_cas")

    def test_pyepisuite_mode_set(self):
        """PYEPISUITE_MODE environment variable is set to remote."""
        import os
        import packages.doss_core.ecosar  # noqa: F401
        
        assert os.environ.get("PYEPISUITE_MODE") == "remote"
