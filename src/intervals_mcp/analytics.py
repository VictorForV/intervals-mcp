"""Turn raw wellness numbers into the qualitative read a coach would give.

intervals.icu reports CTL, ATL and ramp rate as bare numbers. An agent can
recite them, but "TSB is -18" is not itself an answer to "how am I doing" --
a coach reads that against known bands (grey zone, overreaching, fresh) and
checks it against how HRV has been trending. These functions are pure so the
bands can be tested directly against synthetic wellness days, the same way
compact.py is tested against synthetic activities.
"""

from collections.abc import Sequence

# Training Stress Balance = CTL (fitness) - ATL (fatigue). Bands follow the
# common Coggan/Friel convention used across TrainingPeaks-style coaching.
FORM_BANDS = (
    (-30, "high_risk", "Below -30: elevated injury, illness and burnout risk. An easy day or rest is due."),
    (-10, "overreaching", "-30 to -10: hard training zone, sustainable short term but watch for accumulating fatigue."),
    (5, "neutral", "-10 to +5: balanced load, a typical training week."),
    (25, "fresh", "+5 to +25: recovered, a good state for quality sessions or racing."),
    (float("inf"), "very_fresh", "Above +25: well rested, but risk of detraining if sustained."),
)

# CTL points gained per week. Coggan's rule of thumb caps a sustainable ramp
# around 5-8 depending on the athlete; above that, injury risk climbs fast.
RAMP_BANDS = (
    (0, "declining", "Fitness is dropping. Fine as a taper or planned recovery block, a problem otherwise."),
    (3, "maintaining", "Load is roughly steady."),
    (8, "building", "A solid, sustainable build."),
    (float("inf"), "aggressive", "Ramping faster than most athletes tolerate well. Elevated injury risk."),
)

# An HRV drop this large relative to a longer baseline is the threshold most
# HRV-guided training literature (e.g. Kubios, Firstbeat) treats as a signal
# worth acting on, rather than day-to-day noise.
HRV_DROP_FLAG_PCT = -10.0


def _band(value: float, bands: Sequence[tuple[float, str, str]]) -> tuple[str, str]:
    for ceiling, label, note in bands:
        if value < ceiling:
            return label, note
    label, note = bands[-1][1], bands[-1][2]
    return label, note


def classify_form(tsb: float) -> tuple[str, str]:
    """Classify a TSB value into a label and the coaching note for it."""
    return _band(tsb, FORM_BANDS)


def classify_ramp(rate: float) -> tuple[str, str]:
    """Classify a CTL ramp rate (points/week) into a label and coaching note."""
    return _band(rate, RAMP_BANDS)


def hrv_deviation(recent: Sequence[float], baseline: Sequence[float]) -> dict | None:
    """Compare a recent HRV average against a longer baseline.

    Returns ``None`` when either window has no data to average, since a
    percentage change against zero samples is not meaningful.
    """
    if not recent or not baseline:
        return None
    recent_avg = sum(recent) / len(recent)
    baseline_avg = sum(baseline) / len(baseline)
    if not baseline_avg:
        return None
    pct_change = round((recent_avg - baseline_avg) / baseline_avg * 100, 1)
    return {
        "recent_avg": round(recent_avg, 1),
        "baseline_avg": round(baseline_avg, 1),
        "pct_change": pct_change,
        "below_baseline": pct_change <= HRV_DROP_FLAG_PCT,
    }


def assess_readiness(days: Sequence[dict], recent_days: int = 7) -> dict:
    """Assess current training readiness from a run of wellness days.

    ``days`` must be ordered oldest to newest, as intervals.icu's wellness
    endpoint returns them. The most recent day with both ctl and atl present
    sets current form and ramp rate; HRV compares the last ``recent_days``
    entries against everything older in the window as a baseline.
    """
    dated = [d for d in days if d.get("ctl") is not None and d.get("atl") is not None]
    if not dated:
        return {"error": "No wellness days with ctl/atl in this window to assess."}

    latest = dated[-1]
    ctl, atl = latest["ctl"], latest["atl"]
    tsb = round(ctl - atl, 1)
    form_label, form_note = classify_form(tsb)

    result = {
        "as_of": latest.get("id"),
        "ctl": round(ctl, 1),
        "atl": round(atl, 1),
        "tsb": tsb,
        "form": form_label,
        "form_note": form_note,
    }

    rate = latest.get("rampRate")
    if rate is not None:
        ramp_label, ramp_note = classify_ramp(rate)
        result["ramp_rate"] = round(rate, 1)
        result["ramp"] = ramp_label
        result["ramp_note"] = ramp_note

    hrv_days = [d for d in days if d.get("hrv") is not None]
    recent = [d["hrv"] for d in hrv_days[-recent_days:]]
    baseline = [d["hrv"] for d in hrv_days[:-recent_days]] if len(hrv_days) > recent_days else []
    hrv = hrv_deviation(recent, baseline)
    if hrv:
        result["hrv"] = hrv

    return result
