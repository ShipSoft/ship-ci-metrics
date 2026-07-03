# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileCopyrightText: Copyright CERN for the benefit of the SHiP Collaboration

"""Tests for ship_ci_metrics.compare (pure Python, no ROOT required)."""

import copy
import json
import sys

import pytest

from ship_ci_metrics import compare

CONFIG_YAML = """\
comparison:
  float_tolerance: 1.0e-9
  n_sigma: 3.0
"""


def make_metrics(mean=5.0, entries=1000.0, integral=990.0, tree_entries=100):
    """Build a realistic metrics dictionary as produced by ship-metrics-extract."""
    return {
        "timestamp": "2026-01-01T00:00:00Z",
        "configuration": "ci-test",
        "files": {
            "sim.root": {
                "file_size": 12345,
                "trees": {
                    "events": {
                        "entries": {"value": tree_entries, "compare": "exact"},
                        "branches": {"value": 3, "compare": "exact"},
                    },
                },
                "histograms": {
                    "h_energy": {
                        "entries": {
                            "value": entries,
                            "uncertainty": entries**0.5,
                            "compare": "statistical",
                        },
                        "mean": {"value": mean, "uncertainty": 0.03, "compare": "statistical"},
                        "rms": {"value": 1.0, "uncertainty": 0.02, "compare": "statistical"},
                        "integral": {"value": integral, "compare": "float"},
                    },
                },
            },
        },
    }


class TestCompareMetric:
    def test_exact_match(self):
        ref = {"value": 100, "compare": "exact"}
        assert compare.compare_metric(ref, {"value": 100, "compare": "exact"}, "n") == []

    def test_exact_mismatch(self):
        ref = {"value": 100, "compare": "exact"}
        diffs = compare.compare_metric(ref, {"value": 101, "compare": "exact"}, "n")
        assert len(diffs) == 1
        assert "100" in diffs[0] and "101" in diffs[0]

    def test_float_within_tolerance(self):
        ref = {"value": 1.0, "compare": "float"}
        new = {"value": 1.0 + 1e-12, "compare": "float"}
        assert compare.compare_metric(ref, new, "n", float_tolerance=1e-9) == []

    def test_float_beyond_tolerance(self):
        ref = {"value": 1.0, "compare": "float"}
        new = {"value": 1.1, "compare": "float"}
        diffs = compare.compare_metric(ref, new, "n", float_tolerance=1e-9)
        assert len(diffs) == 1
        assert "Δ=" in diffs[0]

    def test_float_both_zero(self):
        ref = {"value": 0, "compare": "float"}
        assert compare.compare_metric(ref, {"value": 0, "compare": "float"}, "n") == []

    def test_float_zero_reference(self):
        ref = {"value": 0, "compare": "float"}
        assert compare.compare_metric(ref, {"value": 1e-12}, "n", float_tolerance=1e-9) == []
        assert len(compare.compare_metric(ref, {"value": 0.5}, "n", float_tolerance=1e-9)) == 1

    def test_statistical_within_n_sigma(self):
        ref = {"value": 5.0, "uncertainty": 0.1, "compare": "statistical"}
        new = {"value": 5.2, "uncertainty": 0.1, "compare": "statistical"}
        # deviation = 0.2 / sqrt(0.02) ≈ 1.4 sigma < 3 sigma
        assert compare.compare_metric(ref, new, "n", n_sigma=3.0) == []

    def test_statistical_beyond_n_sigma(self):
        ref = {"value": 5.0, "uncertainty": 0.1, "compare": "statistical"}
        new = {"value": 6.0, "uncertainty": 0.1, "compare": "statistical"}
        # deviation = 1.0 / sqrt(0.02) ≈ 7.1 sigma > 3 sigma
        diffs = compare.compare_metric(ref, new, "n", n_sigma=3.0)
        assert len(diffs) == 1
        assert "σ" in diffs[0]

    def test_statistical_no_uncertainties(self):
        ref = {"value": 5.0, "compare": "statistical"}
        assert compare.compare_metric(ref, {"value": 5.0}, "n") == []
        diffs = compare.compare_metric(ref, {"value": 6.0}, "n")
        assert len(diffs) == 1
        assert "no uncertainties" in diffs[0]


class TestCompareMetrics:
    def test_identical(self):
        ref = make_metrics()
        diffs, summary = compare.compare_metrics(ref, copy.deepcopy(ref))
        assert diffs == []
        assert summary["files_compared"] == 1
        assert summary["trees_compared"] == 1
        assert summary["histograms_compared"] == 1
        assert summary["total_differences"] == 0

    def test_statistical_shift_detected(self):
        ref = make_metrics(mean=5.0)
        new = make_metrics(mean=6.0)  # 1.0 / sqrt(2 * 0.03**2) ≈ 24 sigma
        diffs, summary = compare.compare_metrics(ref, new, float_tolerance=1e-9, n_sigma=3.0)
        assert summary["total_differences"] == 1
        assert any("h_energy.mean" in d for d in diffs)

    def test_float_shift_detected(self):
        ref = make_metrics(integral=990.0)
        new = make_metrics(integral=991.0)
        diffs, summary = compare.compare_metrics(ref, new, float_tolerance=1e-9)
        assert summary["total_differences"] == 1
        assert any("h_energy.integral" in d for d in diffs)

    def test_exact_shift_detected(self):
        ref = make_metrics(tree_entries=100)
        new = make_metrics(tree_entries=99)
        diffs, summary = compare.compare_metrics(ref, new)
        assert summary["total_differences"] == 1
        assert any("events.entries" in d for d in diffs)

    def test_missing_file(self):
        ref = make_metrics()
        new = copy.deepcopy(ref)
        del new["files"]["sim.root"]
        diffs, summary = compare.compare_metrics(ref, new)
        assert summary["files_missing"] == 1
        assert any("File missing" in d for d in diffs)

    def test_missing_histogram(self):
        ref = make_metrics()
        new = copy.deepcopy(ref)
        del new["files"]["sim.root"]["histograms"]["h_energy"]
        diffs, summary = compare.compare_metrics(ref, new)
        assert any("Histogram missing" in d for d in diffs)
        assert summary["histograms_compared"] == 0


class TestMain:
    @pytest.fixture
    def config_file(self, tmp_path):
        config = tmp_path / "metrics_config.yaml"
        config.write_text(CONFIG_YAML)
        return config

    def run_main(self, monkeypatch, *argv):
        monkeypatch.setattr(sys, "argv", ["ship-metrics-compare", *argv])
        return compare.main()

    def test_no_differences(self, tmp_path, config_file, monkeypatch, capsys):
        ref = tmp_path / "ref.json"
        new = tmp_path / "new.json"
        ref.write_text(json.dumps(make_metrics()))
        new.write_text(json.dumps(make_metrics()))
        assert self.run_main(monkeypatch, str(ref), str(new), "--config", str(config_file)) == 0
        assert "No differences found" in capsys.readouterr().out

    def test_differences_without_fail_flag(self, tmp_path, config_file, monkeypatch, capsys):
        ref = tmp_path / "ref.json"
        new = tmp_path / "new.json"
        ref.write_text(json.dumps(make_metrics(mean=5.0)))
        new.write_text(json.dumps(make_metrics(mean=6.0)))
        assert self.run_main(monkeypatch, str(ref), str(new), "--config", str(config_file)) == 0
        assert "Differences found" in capsys.readouterr().out

    def test_differences_with_fail_flag(self, tmp_path, config_file, monkeypatch):
        ref = tmp_path / "ref.json"
        new = tmp_path / "new.json"
        ref.write_text(json.dumps(make_metrics(mean=5.0)))
        new.write_text(json.dumps(make_metrics(mean=6.0)))
        assert self.run_main(monkeypatch, str(ref), str(new), "--config", str(config_file), "--fail-on-diff") == 1

    def test_n_sigma_override(self, tmp_path, config_file, monkeypatch):
        ref = tmp_path / "ref.json"
        new = tmp_path / "new.json"
        # ≈ 24 sigma shift: fails at 3 sigma, passes at 100 sigma
        ref.write_text(json.dumps(make_metrics(mean=5.0)))
        new.write_text(json.dumps(make_metrics(mean=6.0)))
        args = [str(ref), str(new), "--config", str(config_file), "--fail-on-diff"]
        assert self.run_main(monkeypatch, *args) == 1
        assert self.run_main(monkeypatch, *args, "--n-sigma", "100") == 0

    def test_config_is_required(self, tmp_path, monkeypatch):
        ref = tmp_path / "ref.json"
        ref.write_text("{}")
        with pytest.raises(SystemExit):
            self.run_main(monkeypatch, str(ref), str(ref))

    def test_missing_input_file(self, tmp_path, config_file, monkeypatch):
        assert self.run_main(monkeypatch, "does-not-exist.json", "nope.json", "--config", str(config_file)) == 1
