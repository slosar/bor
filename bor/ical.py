"""
iCalendar (text/calendar) parsing for Bor email reader.

Wraps the `icalendar` library to pull the essential fields out of a calendar
invite (VEVENT) into a small, display-friendly dataclass.  Using `icalendar`
rather than a hand-rolled parser means the embedded VTIMEZONE definitions are
honoured, so Outlook/Exchange Windows timezone names like "Eastern Standard
Time" resolve to the correct DST-aware offset.

Parsing is defensive: anything unexpected yields None rather than raising, so a
malformed invite never breaks message display.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional, Tuple, Union


@dataclass
class CalendarEvent:
    """Essential fields of a calendar invite (VEVENT)."""

    method: str = ""  # REQUEST, CANCEL, REPLY, PUBLISH, COUNTER, ...
    summary: str = ""
    location: str = ""
    organizer: str = ""  # display name, falling back to email
    organizer_email: str = ""
    status: str = ""  # CONFIRMED, TENTATIVE, CANCELLED
    start: Optional[Union[datetime, date]] = None
    end: Optional[Union[datetime, date]] = None
    all_day: bool = False
    recurrence: str = ""  # human-readable RRULE summary, if any


def _coerce_dt(value: object) -> Tuple[Optional[Union[datetime, date]], bool]:
    """Return (datetime-or-date, all_day) for an icalendar DTSTART/DTEND value."""
    if isinstance(value, datetime):
        return value, False
    if isinstance(value, date):
        # A bare date means an all-day event.
        return value, True
    return None, False


def _describe_rrule(rrule: object) -> str:
    """Build a short human-readable summary of a recurrence rule."""
    try:
        freq = rrule.get("FREQ")
        if isinstance(freq, (list, tuple)):
            freq = freq[0] if freq else None
        if not freq:
            return "Recurring"
        interval = rrule.get("INTERVAL")
        if isinstance(interval, (list, tuple)):
            interval = interval[0] if interval else None
        interval = int(interval) if interval else 1
        freq = str(freq).lower()
        unit = {
            "daily": "day",
            "weekly": "week",
            "monthly": "month",
            "yearly": "year",
        }.get(freq, freq)
        if interval == 1:
            return f"Repeats every {unit}"
        return f"Repeats every {interval} {unit}s"
    except Exception:
        return "Recurring"


def parse_calendar(ical_text: str) -> Optional[CalendarEvent]:
    """
    Parse a text/calendar payload into a CalendarEvent.

    Args:
        ical_text: The decoded text of the text/calendar MIME part.

    Returns:
        CalendarEvent for the first VEVENT found, or None if the payload could
        not be parsed, the `icalendar` library is unavailable, or there is no
        VEVENT.
    """
    try:
        from icalendar import Calendar
    except ImportError:
        return None

    try:
        cal = Calendar.from_ical(ical_text)
    except Exception:
        return None

    method = str(cal.get("METHOD") or "").upper()

    try:
        events = list(cal.walk("VEVENT"))
    except Exception:
        return None

    for comp in events:
        ev = CalendarEvent(method=method)
        try:
            ev.summary = str(comp.get("SUMMARY") or "").strip()
            ev.location = str(comp.get("LOCATION") or "").strip()
            ev.status = str(comp.get("STATUS") or "").strip()

            org = comp.get("ORGANIZER")
            if org is not None:
                cn = ""
                params = getattr(org, "params", None)
                if params:
                    cn = str(params.get("CN") or "").strip()
                raw = str(org).strip()
                email = raw[7:] if raw.lower().startswith("mailto:") else raw
                ev.organizer_email = email
                ev.organizer = cn or email

            dtstart = comp.get("DTSTART")
            if dtstart is not None:
                ev.start, ev.all_day = _coerce_dt(dtstart.dt)

            dtend = comp.get("DTEND")
            if dtend is not None:
                ev.end, _ = _coerce_dt(dtend.dt)

            rrule = comp.get("RRULE")
            if rrule:
                ev.recurrence = _describe_rrule(rrule)
        except Exception:
            # Return whatever we managed to extract rather than nothing.
            pass

        return ev

    return None
