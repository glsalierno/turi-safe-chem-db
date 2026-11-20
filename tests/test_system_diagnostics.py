import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from packages.doss_core.system_diagnostics import active_overrides, bundled_database, dependency_versions


class SystemDiagnosticsTests(unittest.TestCase):
    def test_bundled_sqlite_states(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "sample.sqlite"
            self.assertEqual(bundled_database(database), {"status": "missing"})
            database.write_text("version https://git-lfs.github.com/spec/v1\n")
            self.assertEqual(bundled_database(database), {"status": "present but not SQLite"})
            database.unlink()
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("CREATE TABLE by_cas (cas TEXT)")
                connection.execute("INSERT INTO by_cas VALUES ('67-64-1')")
                connection.commit()
            self.assertEqual(bundled_database(database), {"status": "available", "rows": 1})

    def test_only_allowlisted_override_names_are_rendered(self):
        with patch.dict(os.environ, {"EXPERT_P2OASYS_CSV": "/hidden/overlay.csv", "TOKEN": "hidden"}):
            self.assertEqual(active_overrides(("EXPERT_P2OASYS_CSV",)), ["EXPERT_P2OASYS_CSV"])

    def test_versions_and_source_version_fallback(self):
        versions = dependency_versions("nonexistent-test-distribution", "fixture")
        self.assertEqual(versions["nonexistent-test-distribution"], "fixture")
        self.assertIn("Python", versions)
