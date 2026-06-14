"""Fraud detection heuristics — pure functions.

Flags suspicious patterns in channel metrics.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FraudFlag:
    """A fraud signal with severity and explanation."""

    code: str
    severity: str  # "high" | "medium" | "low"
    message: str


def detect_fraud(
    subscribers: int | None = None,
    reach: int | None = None,
    er_pct: float | None = None,
    views_avg: float | None = None,
    subscriber_growth_30d_pct: float | None = None,
) -> list[FraudFlag]:
    """Run all fraud heuristics and return a list of flags.

    All inputs are optional — only available signals are checked.
    """
    flags: list[FraudFlag] = []

    # --- Reach/Subscribers ratio ---
    if subscribers and reach and subscribers > 0:
        ratio = reach / subscribers
        if ratio < 0.05:
            flags.append(FraudFlag(
                code="LOW_REACH_RATIO",
                severity="high",
                message=f"Reach/subs ratio extremely low ({ratio:.1%}) — likely dead or bot subscribers",
            ))
        elif ratio < 0.15:
            flags.append(FraudFlag(
                code="LOW_REACH_RATIO",
                severity="medium",
                message=f"Reach/subs ratio below average ({ratio:.1%})",
            ))
        elif ratio > 1.5:
            flags.append(FraudFlag(
                code="HIGH_REACH_RATIO",
                severity="medium",
                message=f"Reach/subs ratio unusually high ({ratio:.1%}) — possible view bots or viral content",
            ))

    # --- Anomalous engagement rate ---
    if er_pct is not None:
        if er_pct > 30:
            flags.append(FraudFlag(
                code="EXTREME_ER",
                severity="high",
                message=f"Engagement rate {er_pct:.1f}% is abnormally high — likely manipulated",
            ))
        elif er_pct > 15:
            flags.append(FraudFlag(
                code="HIGH_ER",
                severity="medium",
                message=f"Engagement rate {er_pct:.1f}% is unusually high for the niche",
            ))
        elif er_pct < 0.3 and subscribers and subscribers > 1000:
            flags.append(FraudFlag(
                code="LOW_ER",
                severity="medium",
                message=f"Engagement rate {er_pct:.1f}% is very low for channel size ({subscribers:,} subs)",
            ))

    # --- Sudden subscriber growth ---
    if subscriber_growth_30d_pct is not None:
        if subscriber_growth_30d_pct > 100:
            flags.append(FraudFlag(
                code="GROWTH_SPIKE",
                severity="high",
                message=f"Subscriber growth {subscriber_growth_30d_pct:.0f}% in 30 days — likely bought",
            ))
        elif subscriber_growth_30d_pct > 50:
            flags.append(FraudFlag(
                code="GROWTH_SPIKE",
                severity="medium",
                message=f"Subscriber growth {subscriber_growth_30d_pct:.0f}% in 30 days — verify source",
            ))

    # --- Views vs subscribers sanity ---
    if views_avg is not None and subscribers and subscribers > 0:
        view_ratio = views_avg / subscribers
        if view_ratio < 0.01:
            flags.append(FraudFlag(
                code="DEAD_VIEWS",
                severity="high",
                message=f"Average views {views_avg:.0f} on {subscribers:,} subs ({view_ratio:.2%}) — ghost audience",
            ))

    return flags
