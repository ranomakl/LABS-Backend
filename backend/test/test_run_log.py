# -*- test-case-name: backend.test.test_run_log -*-
"""/api/run_log (Setup.remote_run_log -> run_log_lesen): lauf.json + values.json eines Laufs fuer das Frontend
(Excel-Versuchsplan befuellen, 18.11.2026). Ohne laufendes Setup, nur die Suche im Log-Ordner."""
import json
import tempfile
from pathlib import Path

from twisted.trial import unittest

from backend.setup.setup import run_log_lesen


class RunLogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.lauf = self.tmp / "2026" / "11" / "18" / "Design-Stage-7"
        self.lauf.mkdir(parents=True)
        (self.lauf / "lauf.json").write_text(json.dumps({"experiment_id": "Design-Stage-7", "starting_time": 1.0,
                                                          "finishing_time": 2.0}), encoding="utf-8")
        (self.lauf / "values.json").write_text(json.dumps({"pump1": {"dosed_ml": [[1.5, 0.2]]}}), encoding="utf-8")

    def test_lauf_gefunden(self):
        out = run_log_lesen("Design-Stage-7", self.tmp)
        self.assertEqual(out["experiment_id"], "Design-Stage-7")
        self.assertEqual(out["lauf"]["finishing_time"], 2.0)
        self.assertEqual(out["values"]["pump1"]["dosed_ml"], [[1.5, 0.2]])
        self.assertTrue(out["ordner"].endswith("Design-Stage-7"))

    def test_unbekannter_lauf(self):
        self.assertIn("error", run_log_lesen("gibt-es-nicht", self.tmp))

    def test_pfadtrenner_abgelehnt(self):
        for name in ("../../etc", "a/b", "a\\\\b", "..", ""):
            self.assertIn("error", run_log_lesen(name, self.tmp), name)

    def test_values_fehlt(self):
        (self.lauf / "values.json").unlink()
        out = run_log_lesen("Design-Stage-7", self.tmp)
        self.assertIn("values.json fehlt", out["error"])

    def test_neuester_treffer_bei_mehreren(self):
        alt = self.tmp / "2026" / "11" / "10" / "Design-Stage-7"
        alt.mkdir(parents=True)
        (alt / "lauf.json").write_text(json.dumps({"starting_time": 0.5}), encoding="utf-8")
        (alt / "values.json").write_text("{}", encoding="utf-8")
        import os, time
        os.utime(alt, (1, 1))                       # alt = aelter als der Lauf vom 18.
        out = run_log_lesen("Design-Stage-7", self.tmp)
        self.assertEqual(out["lauf"]["finishing_time"], 2.0)
