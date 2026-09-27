"""Retrospective transit research: how each asset has historically behaved
around planetary transits, and whether any of it beats chance.

This is research output, not a live signal. It runs as its own job
(scripts/build_playbook.py), never inside the hourly runner.

    series.py          load completed daily bars + ephemeris as arrays
    transit_events.py  sign ingresses and retrograde stations
    outcomes.py        multi-horizon forward returns, percentile-based labels
    patterns.py        the hypothesis list (which patterns get tested)
    significance.py    circular-shift null, exact uniform-date check, BH FDR
    confidence.py      sample size + effect + corrected significance -> label
    exceptions.py      per-occurrence context for the ones that didn't fit
    sideways.py        which transit states coincide with chop
    playbook.py        assembles and persists the per-asset playbook
"""
