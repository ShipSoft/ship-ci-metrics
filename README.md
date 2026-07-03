<!--
SPDX-License-Identifier: LGPL-3.0-or-later
SPDX-FileCopyrightText: Copyright CERN for the benefit of the SHiP Collaboration
-->

# ship-ci-metrics

CI tooling for the SHiP experiment: extract lightweight physics metrics from
ROOT files, compare them across commits, render validation plots, and
summarise the results in pull request comments. Extracted from FairShip's
`.github/scripts/` so all SHiP frameworks can share one implementation.

## Commands

| Command | Purpose |
|---|---|
| `ship-metrics-extract <dir> --config <yaml> [-o out.json] [--pretty]` | Extract tree/histogram/fit metrics from the ROOT files listed in the config into compact JSON. |
| `ship-metrics-compare <ref.json> <new.json> --config <yaml> [--fail-on-diff]` | Compare two metrics files; each metric declares its own comparison mode. Tolerances come from the config, overridable via `--float-tolerance`/`--n-sigma`. |
| `ship-metrics-render <files...> --output-dir <dir> --job <name> --config <label>` | Render drawable ROOT objects to PNGs plus a `manifest.json`. |
| `ship-metrics-pr-comment <dir> [-o comment.md]` | Turn a directory of `comparison_*.txt` results into a markdown PR comment. |

`extract` and `render` need PyROOT at runtime (`root_base` on conda-forge);
it is deliberately not declared as a package dependency so `compare` and
`pr-comment` stay usable in minimal environments.

## Configuration

Each consumer repository ships its own `metrics_config.yaml`, passed via
`--config`:

```yaml
files:
  process:            # ROOT files to extract metrics from
    - sim_ci-test.root
    - recohists.root
extraction:
  max_histogram_depth: 2   # directory recursion depth
  fit_functions: [gaus, pol1, expo]  # fit names to look for on histograms
comparison:
  float_tolerance: 1.0e-9  # relative tolerance for compare="float"
  n_sigma: 3.0             # threshold for compare="statistical"
```

Comparison modes per metric: `exact` (must match), `float` (relative
tolerance), `statistical` (agreement within combined uncertainties).

## Development

```console
pixi run test              # pytest (includes PyROOT round-trip tests)
pixi run -e lint lint      # prek: ruff, codespell, reuse, cff, ...
pixi run -e lint install-hooks  # one-off: install git hooks
```
