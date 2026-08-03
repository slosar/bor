"""Tests for iCalendar (text/calendar) parsing and rendering.

Covers `bor.ical.parse_calendar` (extraction of VEVENT fields, including
DST-aware timezone resolution from embedded VTIMEZONE / Windows tz names) and
`bor.tabs.message.format_calendar_event` (the styled block shown above the
message body).
"""

from __future__ import annotations

from datetime import date, datetime

from rich.text import Text

from bor.ical import CalendarEvent, parse_calendar
from bor.tabs.message import format_calendar_event

# A timed Outlook/Exchange invite using a Windows timezone name. The embedded
# VTIMEZONE lets icalendar resolve "Eastern Standard Time" to the correct
# DST-aware offset (EDT / UTC-04:00 in late June).
TIMED_INVITE = """BEGIN:VCALENDAR
METHOD:REQUEST
PRODID:Microsoft Exchange Server 2010
VERSION:2.0
BEGIN:VTIMEZONE
TZID:Eastern Standard Time
BEGIN:STANDARD
DTSTART:16010101T020000
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
RRULE:FREQ=YEARLY;INTERVAL=1;BYDAY=1SU;BYMONTH=11
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:16010101T020000
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
RRULE:FREQ=YEARLY;INTERVAL=1;BYDAY=2SU;BYMONTH=3
END:DAYLIGHT
END:VTIMEZONE
BEGIN:VEVENT
ORGANIZER;CN="Parker, Melanie":mailto:ParkerM3@AETNA.com
SUMMARY;LANGUAGE=en-US:Brookhaven/Aetna International Member Webinar
DTSTART;TZID=Eastern Standard Time:20260624T093000
DTEND;TZID=Eastern Standard Time:20260624T103000
LOCATION;LANGUAGE=en-US:Microsoft Teams Meeting
STATUS:CONFIRMED
END:VEVENT
END:VCALENDAR"""

ALL_DAY_INVITE = """BEGIN:VCALENDAR
METHOD:REQUEST
BEGIN:VEVENT
SUMMARY:Team Offsite
DTSTART;VALUE=DATE:20260701
DTEND;VALUE=DATE:20260703
LOCATION:HQ
ORGANIZER;CN=Jane Doe:mailto:jane@example.com
RRULE:FREQ=WEEKLY;INTERVAL=2
STATUS:CONFIRMED
END:VEVENT
END:VCALENDAR"""


def test_parse_timed_invite_fields():
    ev = parse_calendar(TIMED_INVITE)
    assert ev is not None
    assert ev.method == "REQUEST"
    assert ev.summary == "Brookhaven/Aetna International Member Webinar"
    assert ev.location == "Microsoft Teams Meeting"
    assert ev.status == "CONFIRMED"
    assert ev.organizer == "Parker, Melanie"
    assert ev.organizer_email == "ParkerM3@AETNA.com"
    assert not ev.all_day


def test_parse_timed_invite_timezone_is_dst_aware():
    ev = parse_calendar(TIMED_INVITE)
    assert isinstance(ev.start, datetime)
    assert ev.start.tzinfo is not None
    # June 24 is in daylight saving time → EDT / UTC-04:00.
    assert ev.start.utcoffset().total_seconds() == -4 * 3600
    assert ev.start.hour == 9 and ev.start.minute == 30
    assert ev.end.hour == 10 and ev.end.minute == 30


def test_parse_all_day_invite():
    ev = parse_calendar(ALL_DAY_INVITE)
    assert ev is not None
    assert ev.all_day
    assert isinstance(ev.start, date) and not isinstance(ev.start, datetime)
    assert ev.start == date(2026, 7, 1)
    assert ev.recurrence  # RRULE present → some human description
    assert "2" in ev.recurrence and "week" in ev.recurrence


def test_parse_invalid_returns_none():
    assert parse_calendar("not a calendar at all") is None
    assert parse_calendar("") is None


def test_format_timed_invite_renders_expected_text():
    ev = parse_calendar(TIMED_INVITE)
    rendered = format_calendar_event(ev)
    assert isinstance(rendered, Text)
    plain = rendered.plain
    assert "Calendar Invitation" in plain
    assert "Brookhaven/Aetna International Member Webinar" in plain
    assert "Wednesday, June 24, 2026" in plain
    assert "9:30 AM" in plain and "10:30 AM" in plain
    assert "Microsoft Teams Meeting" in plain
    assert "Parker, Melanie" in plain
    assert "Confirmed" in plain


def test_format_cancel_method_title():
    ev = CalendarEvent(method="CANCEL", summary="Cancelled Meeting")
    plain = format_calendar_event(ev).plain
    assert "CANCELLED" in plain


def test_format_all_day_collapses_exclusive_end():
    ev = parse_calendar(ALL_DAY_INVITE)
    plain = format_calendar_event(ev).plain
    # DTEND (July 3) is exclusive, so the visible range ends July 2.
    assert "all day" in plain
    assert "July 1, 2026" in plain
    assert "July 2, 2026" in plain
    assert "July 3, 2026" not in plain
