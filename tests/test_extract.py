# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileCopyrightText: Copyright CERN for the benefit of the SHiP Collaboration

"""Tests for ship_ci_metrics.extract (require PyROOT)."""

import array
import json
import math
import sys

import pytest

ROOT = pytest.importorskip("ROOT")

from ship_ci_metrics import extract  # noqa: E402

N_HIST = 1000
N_TREE = 50

CONFIG_YAML = """\
files:
  process:
    - sim.root
extraction:
  max_histogram_depth: 2
  fit_functions:
    - gaus
comparison:
  float_tolerance: 1.0e-9
  n_sigma: 3.0
"""


@pytest.fixture
def data_dir(tmp_path):
    """Create a small ROOT file with a filled TH1, a fitted TH1, and a TTree."""
    ROOT.gROOT.SetBatch(True)
    root_file = ROOT.TFile(str(tmp_path / "sim.root"), "RECREATE")

    rng = ROOT.TRandom3(12345)
    h_energy = ROOT.TH1D("h_energy", "Energy;E [GeV];Entries", 100, 0, 10)
    for _ in range(N_HIST):
        h_energy.Fill(rng.Gaus(5.0, 1.0))
    h_energy.Fit("gaus", "Q")
    h_energy.Write()

    subdir = root_file.mkdir("hists")
    subdir.cd()
    h_hits = ROOT.TH1D("h_hits", "Hits", 10, 0, 10)
    for _ in range(N_HIST):
        h_hits.Fill(rng.Uniform(0, 10))
    h_hits.Write()
    root_file.cd()

    tree = ROOT.TTree("events", "events")
    x = array.array("d", [0.0])
    tree.Branch("x", x, "x/D")
    for i in range(N_TREE):
        x[0] = float(i)
        tree.Fill()
    tree.Write()

    root_file.Close()
    return tmp_path


@pytest.fixture
def config_file(tmp_path):
    config = tmp_path / "metrics_config.yaml"
    config.write_text(CONFIG_YAML)
    return config


def test_extract_main(data_dir, config_file, monkeypatch):
    output = data_dir / "metrics.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ship-metrics-extract",
            str(data_dir),
            "-o",
            str(output),
            "--pretty",
            "--config",
            str(config_file),
        ],
    )
    assert extract.main() == 0

    metrics = json.loads(output.read_text())
    assert metrics["configuration"] == data_dir.name
    assert set(metrics["files"]) == {"sim.root"}

    file_metrics = metrics["files"]["sim.root"]
    assert file_metrics["file_size"] > 0

    # TTree metrics
    tree = file_metrics["trees"]["events"]
    assert tree["entries"] == {"value": N_TREE, "compare": "exact"}
    assert tree["branches"] == {"value": 1, "compare": "exact"}

    # Top-level histogram metrics
    h_energy = file_metrics["histograms"]["h_energy"]
    assert h_energy["entries"]["value"] == N_HIST
    assert h_energy["entries"]["compare"] == "statistical"
    assert h_energy["entries"]["uncertainty"] == pytest.approx(math.sqrt(N_HIST))
    assert h_energy["mean"]["value"] == pytest.approx(5.0, abs=0.2)
    assert h_energy["rms"]["value"] == pytest.approx(1.0, abs=0.2)
    assert h_energy["integral"]["compare"] == "float"
    assert 0 < h_energy["integral"]["value"] <= N_HIST

    # Fit metrics from the attached gaus fit
    fit = h_energy["fit"]
    assert fit["type"] == {"value": "gaus", "compare": "exact"}
    assert fit["parameters"]["Mean"]["value"] == pytest.approx(5.0, abs=0.2)
    assert fit["parameters"]["Sigma"]["value"] == pytest.approx(1.0, abs=0.2)
    assert fit["parameters"]["Mean"]["compare"] == "statistical"

    # Histogram in a subdirectory (depth 2)
    assert file_metrics["histograms"]["hists/h_hits"]["entries"]["value"] == N_HIST


def test_extract_respects_max_depth(data_dir, tmp_path, monkeypatch):
    config = tmp_path / "shallow_config.yaml"
    config.write_text(CONFIG_YAML.replace("max_histogram_depth: 2", "max_histogram_depth: 1"))
    output = data_dir / "metrics_shallow.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["ship-metrics-extract", str(data_dir), "-o", str(output), "--config", str(config)],
    )
    assert extract.main() == 0

    histograms = json.loads(output.read_text())["files"]["sim.root"]["histograms"]
    assert "h_energy" in histograms
    assert "hists/h_hits" not in histograms


def test_missing_directory_fails(config_file, monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["ship-metrics-extract", "does-not-exist", "--config", str(config_file)],
    )
    assert extract.main() == 1


def test_config_is_required(data_dir, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["ship-metrics-extract", str(data_dir)])
    with pytest.raises(SystemExit):
        extract.main()


def test_invalid_config_rejected(data_dir, tmp_path, monkeypatch):
    config = tmp_path / "bad_config.yaml"
    config.write_text("files:\n  process: [sim.root]\n")
    monkeypatch.setattr(
        sys,
        "argv",
        ["ship-metrics-extract", str(data_dir), "--config", str(config)],
    )
    with pytest.raises(ValueError, match="Missing required config section"):
        extract.main()
