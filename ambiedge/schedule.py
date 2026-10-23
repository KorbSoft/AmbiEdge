"""Daily on/off times."""

import re

TIME = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
CHOICES = tuple(f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 30))


def parse(text):
    """'HH:MM' -> minutes after midnight, or None if it isn't a valid time."""
    m = TIME.match(text.strip()) if isinstance(text, str) else None
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def is_on(on_time, off_time, now):
    """Whether `now` (a datetime) falls between the on and off times. Handles overnight spans."""
    on, off = parse(on_time), parse(off_time)
    if on is None or off is None or on == off:
        return True
    minute = now.hour * 60 + now.minute
    if on < off:
        return on <= minute < off
    return minute >= on or minute < off
