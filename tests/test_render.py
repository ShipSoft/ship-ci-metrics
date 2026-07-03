# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileCopyrightText: Copyright CERN for the benefit of the SHiP Collaboration

"""Tests for ship_ci_metrics.render (require PyROOT)."""

import json
import sys

import pytest

ROOT = pytest.importorskip("ROOT")

from ship_ci_metrics import render  # noqa: E402


@pytest.fixture
def root_file(tmp_path):
    """Create a small ROOT file with drawable and non-drawable objects."""
    ROOT.gROOT.SetBatch(True)
    path = tmp_path / "hists.root"
    f = ROOT.TFile(str(path), "RECREATE")

    rng = ROOT.TRandom3(12345)
    h1 = ROOT.TH1D("h_energy", "Energy", 50, 0, 10)
    for _ in range(500):
        h1.Fill(rng.Gaus(5.0, 1.0))
    h1.Write()

    subdir = f.mkdir("sub")
    subdir.cd()
    h2 = ROOT.TH1D("h_hits", "Hits", 10, 0, 10)
    h2.Fill(3.0)
    h2.Write()
    f.cd()

    # Not drawable: should be skipped without failing
    vec = ROOT.TVectorD(3)
    vec.Write("v_params")

    f.Close()
    return path


def test_render_main(root_file, tmp_path, monkeypatch):
    output_dir = tmp_path / "plots"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ship-metrics-render",
            str(root_file),
            "--output-dir",
            str(output_dir),
            "--job",
            "test-job",
            "--config",
            "ci-test",
        ],
    )
    assert render.main() == 0

    manifest = json.loads((output_dir / "manifest.json").read_text())
    assert manifest["job"] == "test-job"
    assert manifest["config"] == "ci-test"

    rendered = {entry["root_path"]: entry for entry in manifest["files"]}
    assert set(rendered) == {"h_energy", "sub/h_hits"}
    assert rendered["h_energy"]["type"] == "TH1D"

    for entry in manifest["files"]:
        png = output_dir / entry["file"]
        assert png.exists()
        assert png.stat().st_size > 0


def test_render_nothing_drawable(tmp_path, monkeypatch):
    path = tmp_path / "empty.root"
    f = ROOT.TFile(str(path), "RECREATE")
    f.Close()

    output_dir = tmp_path / "plots"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ship-metrics-render",
            str(path),
            "--output-dir",
            str(output_dir),
            "--job",
            "test-job",
            "--config",
            "ci-test",
        ],
    )
    assert render.main() == 1
    assert not (output_dir / "manifest.json").exists()


def test_sanitise_filename():
    assert render._sanitise_filename("sub/h_hits") == "sub_h_hits"
    assert render._sanitise_filename("h(E) [GeV]") == "h_E___GeV_"
