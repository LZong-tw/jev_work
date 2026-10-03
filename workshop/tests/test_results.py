"""results/run_all.py + results/report.py, on the offline mock (the real run costs money)."""
import json
import shutil
import tempfile
import unittest
import xml.dom.minidom
from pathlib import Path

from helpers import run_script


class ResultsPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = Path(tempfile.mkdtemp(prefix="jev-results-"))
        cls.measured = run_script("results/run_all.py", "--repeats", "1", timeout=600, JEV_MOCK=1,
                             RESULTS_ALLOW_MOCK=1, RESULTS_DIR=cls.out)
        cls.report = run_script("results/report.py", RESULTS_DIR=cls.out)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.out, ignore_errors=True)

    def test_refuses_mock_mode_by_default(self):
        r = run_script("results/run_all.py", "--levels", "1", JEV_MOCK=1, RESULTS_DIR=self.out / "no")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("measures the real API", r.stdout + r.stderr)

    def test_every_level_is_measured(self):
        self.assertEqual(self.measured.returncode, 0, self.measured.stdout + self.measured.stderr)
        for n in range(1, 6):
            data = json.loads((self.out / f"level{n}.json").read_text())
            self.assertEqual(data["level"], n)
            self.assertGreater(data["calls"], 0)
        l4 = json.loads((self.out / "level4.json").read_text())["data"]
        self.assertEqual(l4["best possible"][0]["1"], 72)
        self.assertEqual(l4["rules (no AI)"][0]["2"], 30)
        l5 = json.loads((self.out / "level5.json").read_text())["data"]
        rules = l5["configs"]["simple rules (no AI)"][0]
        self.assertEqual(rules["score"], 165.3)
        self.assertEqual(len(rules["blocks"]), 4)  # points per 50 ticks
        self.assertEqual(rules["tokens"], 0)
        jev_runs = l5["configs"]["Jev, full history (starter)"]
        self.assertGreater(jev_runs[0]["calls"], 100)
        self.assertEqual(set(l5["configs"]), {"fixed timer (no AI)", "simple rules (no AI)", "Jev, current tick only",
                                              "Jev, full history (starter)", "A: history + coach lessons",
                                              "B: last 20 ticks + lessons"})

    def test_report_has_every_level_and_valid_charts(self):
        self.assertEqual(self.report.returncode, 0, self.report.stderr)
        text = (self.out / "RESULTS.md").read_text()
        for n in range(1, 6):
            self.assertIn(f"## Level {n}", text)
        for chart in ("level2", "level3", "level4", "level5", "level5-energy"):
            svg = self.out / "charts" / f"{chart}.svg"
            self.assertIn(f"charts/{chart}.svg", text)
            xml.dom.minidom.parse(str(svg))  # well-formed
            self.assertIn("prefers-color-scheme: dark", svg.read_text())


if __name__ == "__main__":
    unittest.main()
