# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileCopyrightText: Copyright CERN for the benefit of the SHiP Collaboration

"""Tests for ship_ci_metrics.pr_comment (pure Python, no ROOT required)."""

import sys

from ship_ci_metrics import pr_comment

NO_REFERENCE = """\
No reference metrics found for commit 0123456789abcdef
"""

# Clean run, as written by `ship-metrics-compare` (trimmed header).
NO_DIFF = """\
================================================================================
Physics Metrics Comparison
================================================================================

Reference: reference.json
New:       new.json
Float tolerance: 1e-09
N-sigma:         3.0

--------------------------------------------------------------------------------
Summary:
  Files compared:      2
  Files missing:       0
  Trees compared:      2
  Histograms compared: 12
  Fits compared:       1

  Total differences:   0

No differences found
================================================================================
"""

HAS_DIFF = """\
================================================================================
Physics Metrics Comparison
================================================================================

Reference: reference.json
New:       new.json
Float tolerance: 1e-09
N-sigma:         3.0

--------------------------------------------------------------------------------
Summary:
  Files compared:      1
  Files missing:       0
  Trees compared:      1
  Histograms compared: 3
  Fits compared:       1

  Total differences:   2

--------------------------------------------------------------------------------
Differences found:

sim.root:
  h_energy.mean: 5±0.03 → 6±0.03 (23.6σ)
  h_energy.integral: 990 → 991 (Δ=0.101%)
================================================================================
"""


class TestParseComparisonFile:
    def test_no_reference(self, tmp_path):
        f = tmp_path / "comparison_a.txt"
        f.write_text(NO_REFERENCE)
        result = pr_comment.parse_comparison_file(f)
        assert result["status"] == "no_reference"

    def test_no_diff(self, tmp_path):
        f = tmp_path / "comparison_a.txt"
        f.write_text(NO_DIFF)
        result = pr_comment.parse_comparison_file(f)
        assert result["status"] == "no_diff"
        assert result["summary"] == {"files": 2, "histograms": 12, "fits": 1}

    def test_has_diff(self, tmp_path):
        f = tmp_path / "comparison_a.txt"
        f.write_text(HAS_DIFF)
        result = pr_comment.parse_comparison_file(f)
        assert result["status"] == "has_diff"
        assert result["total_differences"] == 2
        assert result["summary"] == {"files": 1, "histograms": 3, "fits": 1}
        assert len(result["differences"]) == 2
        assert result["differences"][0]["file"] == "sim.root"
        assert "h_energy.mean" in result["differences"][0]["description"]


class TestGenerateComment:
    def test_empty_directory(self, tmp_path):
        assert pr_comment.generate_comment(tmp_path) == "No comparison results found"

    def test_all_no_reference(self, tmp_path):
        (tmp_path / "comparison_ci-test.txt").write_text(NO_REFERENCE)
        comment = pr_comment.generate_comment(tmp_path)
        assert "First run" in comment
        assert "Configurations compared: 1" in comment

    def test_all_match(self, tmp_path):
        (tmp_path / "comparison_ci-test.txt").write_text(NO_DIFF)
        comment = pr_comment.generate_comment(tmp_path)
        assert "All configurations match reference" in comment
        assert "Matching reference: 1" in comment

    def test_with_differences(self, tmp_path):
        (tmp_path / "comparison_ci-test.txt").write_text(HAS_DIFF)
        (tmp_path / "comparison_other.txt").write_text(NO_DIFF)
        comment = pr_comment.generate_comment(tmp_path)
        assert "1 configuration(s) have differences" in comment
        assert "Configurations compared: 2" in comment
        assert "Matching reference: 1" in comment
        assert "With differences: 1" in comment
        assert "**Total differences: 2**" in comment
        assert "h_energy.mean" in comment

    def test_mixed_reference_and_diff(self, tmp_path):
        (tmp_path / "comparison_a.txt").write_text(NO_REFERENCE)
        (tmp_path / "comparison_b.txt").write_text(HAS_DIFF)
        comment = pr_comment.generate_comment(tmp_path)
        assert "1 configuration(s) have differences" in comment
        assert "No reference available: 1" in comment


class TestMain:
    def test_writes_output_file(self, tmp_path, monkeypatch):
        comp_dir = tmp_path / "comparisons"
        comp_dir.mkdir()
        (comp_dir / "comparison_ci-test.txt").write_text(NO_DIFF)
        output = tmp_path / "comment.md"
        monkeypatch.setattr(sys, "argv", ["ship-metrics-pr-comment", str(comp_dir), "-o", str(output)])
        assert pr_comment.main() == 0
        assert "Physics Metrics Comparison" in output.read_text()

    def test_stdout(self, tmp_path, monkeypatch, capsys):
        (tmp_path / "comparison_ci-test.txt").write_text(NO_REFERENCE)
        monkeypatch.setattr(sys, "argv", ["ship-metrics-pr-comment", str(tmp_path)])
        assert pr_comment.main() == 0
        assert "First run" in capsys.readouterr().out
