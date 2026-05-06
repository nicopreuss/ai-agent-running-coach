"""SQL query functions for the agent's data tools.

Each function accepts a SQLAlchemy Connection and returns a formatted plain-text string
that the LLM reads directly as tool output.
"""

from sqlalchemy import text
from sqlalchemy.engine import Connection


def get_training_and_recovery(conn: Connection, lookback_days: int = 7) -> str:
    """Return formatted training and recovery data for the last *lookback_days* days."""
    if lookback_days > 90:
        return (
            "Error: maximum lookback is 90 days (3 months). "
            "Ask the user to confirm a shorter window."
        )

    rows = (
        conn.execute(
            text(
                """
                SELECT
                    w.date,
                    w.recovery_score,
                    w.hrv_rmssd_ms,
                    w.resting_heart_rate,
                    w.sleep_performance_pct,
                    w.sleep_duration_ms,
                    w.daily_strain,
                    s.name          AS run_name,
                    s.distance_meters,
                    s.duration_seconds,
                    s.avg_pace_sec_per_km,
                    s.avg_heart_rate,
                    s.efficiency_factor
                FROM whoop_recovery_daily w
                LEFT JOIN LATERAL (
                    SELECT name, distance_meters, duration_seconds,
                           avg_pace_sec_per_km, avg_heart_rate, efficiency_factor
                    FROM strava_activities
                    WHERE date = w.date
                    ORDER BY distance_meters DESC NULLS LAST
                    LIMIT 1
                ) s ON TRUE
                WHERE w.date >= CURRENT_DATE - (:lookback_days || ' days')::INTERVAL
                ORDER BY w.date DESC
                """
            ),
            {"lookback_days": lookback_days},
        )
        .mappings()
        .all()
    )

    if not rows:
        return f"No training or recovery data found for the last {lookback_days} days."

    return "\n\n".join(_fmt_day(row) for row in rows)


def get_upcoming_sessions(conn: Connection, days_ahead: int = 7) -> str:
    """Return formatted upcoming planned sessions for the next *days_ahead* days."""
    if days_ahead > 90:
        return (
            "Error: maximum window is 90 days (3 months). "
            "Ask the user to confirm a shorter window."
        )

    rows = (
        conn.execute(
            text(
                """
                SELECT date, title, description
                FROM google_calendar_runna_sessions
                WHERE date >= CURRENT_DATE
                  AND date <= CURRENT_DATE + (:days_ahead || ' days')::INTERVAL
                ORDER BY date ASC
                """
            ),
            {"days_ahead": days_ahead},
        )
        .mappings()
        .all()
    )

    if not rows:
        return f"No upcoming sessions in the next {days_ahead} days."

    return "\n\n".join(_fmt_session(row) for row in rows)


def _fmt_day(row) -> str:
    day_label = row["date"].strftime("%Y-%m-%d (%a)")
    recovery_line = _fmt_recovery(row)
    run_line = _fmt_run(row) if row["distance_meters"] is not None else "No run recorded."
    return f"--- {day_label} ---\n{recovery_line}\n{run_line}"


def _fmt_recovery(row) -> str:
    recovery = f"{row['recovery_score']:.0f}%" if row["recovery_score"] is not None else "N/A"
    hrv = f"{row['hrv_rmssd_ms']:.0f}ms" if row["hrv_rmssd_ms"] is not None else "N/A"
    rhr = f"{row['resting_heart_rate']:.0f}bpm" if row["resting_heart_rate"] is not None else "N/A"
    sleep = _fmt_sleep(row["sleep_performance_pct"], row["sleep_duration_ms"])
    strain = f"{row['daily_strain']:.1f}" if row["daily_strain"] is not None else "N/A"
    parts = [
        f"Recovery: {recovery}",
        f"HRV: {hrv}",
        f"Resting HR: {rhr}",
        f"Sleep: {sleep}",
        f"Strain: {strain}",
    ]
    return " | ".join(parts)


def _fmt_sleep(pct, ms) -> str:
    if pct is None:
        return "N/A"
    label = f"{pct:.0f}%"
    if ms is not None:
        total_min = ms // 60000
        h, m = divmod(total_min, 60)
        label += f" ({h}h {m:02d}m)"
    return label


def _fmt_run(row) -> str:
    km = row["distance_meters"] / 1000
    dur = _fmt_duration(row["duration_seconds"])
    pace = _fmt_pace(row["avg_pace_sec_per_km"])
    hr = f"{row['avg_heart_rate']:.0f}bpm" if row["avg_heart_rate"] is not None else "N/A"
    ef = f"{row['efficiency_factor']:.2f}" if row["efficiency_factor"] is not None else "N/A"
    name = row["run_name"] or "Run"
    return f'Run: "{name}" · {km:.1f}km in {dur} | Pace: {pace} | Avg HR: {hr} | EF: {ef}'


def _fmt_duration(seconds) -> str:
    if seconds is None:
        return "N/A"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _fmt_pace(sec_per_km) -> str:
    if sec_per_km is None:
        return "N/A"
    s = int(sec_per_km)
    return f"{s // 60}:{s % 60:02d}/km"


def _fmt_session(row) -> str:
    day_label = row["date"].strftime("%Y-%m-%d (%a)")
    title = row["title"] or "Untitled session"
    lines = [f"--- {day_label} ---", title]
    if row["description"]:
        lines.append(row["description"])
    return "\n".join(lines)
