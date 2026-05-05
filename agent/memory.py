"""Athlete profile and session notes memory system.

Tier 1 (athlete_profile): permanent facts, always injected into the system prompt.
Tier 2 (session_notes): daily observations, today + yesterday auto-loaded.
"""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.sql import func

from db.client import get_connection
from db.models import AthleteProfile, SessionNote

_DEFAULT_USER = "default"

_ONBOARDING_BLOCK = """\
## CRITICAL: First-Run Onboarding Required
The athlete profile is empty. You MUST begin onboarding immediately, regardless of what \
the user says — even if they just say "hello". Do NOT give a generic greeting response. \
Your very first reply must introduce yourself briefly as their personal running coach, \
then ask question 1 below. Ask questions one at a time. Save each answer to the athlete \
profile using the update_athlete_profile tool before asking the next question. \
Do not ask the next question until the current answer is saved.

1. How long have you been running, and how would you describe your current level?
2. What is your main running goal right now? (race, time target, general fitness, etc.)
3. Do you have any current or recurring injuries I should know about?
4. How many days per week are you currently training?
5. How would you like me to coach you — encouraging and supportive, or direct and data-driven?
6. What should I call you?\
"""


def load_athlete_context(user_id: str = _DEFAULT_USER) -> str:
    """Return the formatted context block to prepend to the system prompt.

    Returns the onboarding block if the profile is missing or empty.
    """
    with get_connection() as conn:
        profile_row = conn.execute(
            select(AthleteProfile.content).where(AthleteProfile.user_id == user_id)
        ).fetchone()
        profile_content = profile_row.content if profile_row else None

        if not profile_content:
            return _ONBOARDING_BLOCK

        today = date.today()
        yesterday = today - timedelta(days=1)
        note_rows = conn.execute(
            select(SessionNote.content)
            .where(SessionNote.user_id == user_id)
            .where(SessionNote.date.in_([today, yesterday]))
            .order_by(SessionNote.date.desc())
        ).fetchall()

        parts = [f"## Athlete Profile\n{profile_content}"]
        if note_rows:
            parts.append("## Recent Session Notes")
            for row in note_rows:
                if row.content:
                    parts.append(row.content)

    return "\n\n".join(parts)


def update_athlete_profile(fact: str, user_id: str = _DEFAULT_USER) -> str:
    """Append *fact* to the athlete's persistent profile in the DB."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    entry = f"\n- [{timestamp}] {fact}"

    with get_connection() as conn:
        conn.execute(
            pg_insert(AthleteProfile)
            .values(user_id=user_id, content=entry, updated_at=func.now())
            .on_conflict_do_update(
                index_elements=["user_id"],
                set_={
                    "content": func.coalesce(AthleteProfile.content, "") + entry,
                    "updated_at": func.now(),
                },
            )
        )
        conn.commit()

    return f"Saved to your profile: {fact}"


def add_session_note(note: str, user_id: str = _DEFAULT_USER) -> str:
    """Append *note* to today's session note row in the DB."""
    today = date.today()
    # date is implicit in session_notes.date column, so time-only timestamp suffices
    timestamp = datetime.now(timezone.utc).strftime("%H:%M UTC")
    entry = f"\n- [{timestamp}] {note}"

    with get_connection() as conn:
        conn.execute(
            pg_insert(SessionNote)
            .values(user_id=user_id, date=today, content=entry, updated_at=func.now())
            .on_conflict_do_update(
                index_elements=["user_id", "date"],
                set_={
                    "content": func.coalesce(SessionNote.content, "") + entry,
                    "updated_at": func.now(),
                },
            )
        )
        conn.commit()

    return "Session note saved."
