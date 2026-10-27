"""
display.py — how numbers are shown: text formatting and status
colours, shared by every window.

Signs are ASCII ("+" / "-"): AC's default font has no Unicode minus.
"""

STATUS_GOOD = "good"
STATUS_WARN = "warn"
STATUS_BAD = "bad"
STATUS_BEST = "best"   # purple: faster than the reference

# RGBA per status, as ac.setFontColor takes them. None = no status.
STATUS_RGBA = {
    STATUS_GOOD: (0.4, 0.9, 0.55, 1.0),
    STATUS_WARN: (1.0, 0.78, 0.3, 1.0),
    STATUS_BAD: (1.0, 0.42, 0.36, 1.0),
    STATUS_BEST: (0.74, 0.45, 1.0, 1.0),
    None: (1.0, 1.0, 1.0, 1.0),
}

NO_VALUE = "--"


def format_litres(value):
    """'51.80 L'."""
    if value is None:
        return NO_VALUE
    return "{:.2f} L".format(value)


def format_fuel_lap(lap):
    """'4.08 L', with the reason appended when the lap is excluded
    from the average, e.g. '4.31 L (pit)'."""
    if lap is None:
        return NO_VALUE
    text = format_litres(lap.fuel_used)
    if not lap.is_valid:
        text += " ({})".format(lap.excluded_reason)
    return text


def format_average(value, lap_count):
    """'4.11 L (5 laps)' so you can see how much data is behind it."""
    if value is None:
        return NO_VALUE
    return "{} ({} laps)".format(format_litres(value), lap_count)


def format_laps(value):
    """'12.6' laps."""
    if value is None:
        return NO_VALUE
    return "{:.1f}".format(value)


def format_surplus(surplus, per_lap):
    """'+2.30 L (+0.6 laps)' / '-4.00 L (-1.0 laps)'."""
    if surplus is None or not per_lap:
        return NO_VALUE
    return "{:+.2f} L ({:+.1f} laps)".format(surplus, surplus / per_lap)


def format_target(target):
    """'3.81 L/lap'."""
    if target is None:
        return NO_VALUE
    return "{:.2f} L/lap".format(target)


def format_current_lap(used, delta):
    """'1.73 L (+0.04)': used so far, then how far over (+) or under
    (-) the target budget for this point of the lap."""
    text = format_litres(used)
    if used is not None and delta is not None:
        text += " ({:+.2f})".format(delta)
    return text


def format_speed(speed_kmh):
    """'187 km/h'."""
    if speed_kmh is None:
        return NO_VALUE
    return "{:.0f} km/h".format(speed_kmh)


def format_gear(gear):
    """AC numbers gears 0 = reverse, 1 = neutral, 2 = first, ..."""
    if gear is None:
        return NO_VALUE
    if gear == 0:
        return "R"
    if gear == 1:
        return "N"
    return str(gear - 1)


def format_lap_time(ms):
    """'1:23.456' (minutes only when there are some: '58.123')."""
    if ms is None or ms < 0:
        return NO_VALUE
    minutes, rest = divmod(int(round(ms)), 60000)
    seconds = rest / 1000.0
    if minutes:
        return "{}:{:06.3f}".format(minutes, seconds)
    return "{:.3f}".format(seconds)


def format_delta(ms):
    """'+0.234' / '-1.050' seconds."""
    if ms is None:
        return NO_VALUE
    return "{:+.3f}".format(ms / 1000.0)


def delta_status(ms):
    """Within 0.05 s of the theoretical best is good, under 0.5 s is
    a warning, beyond that bad."""
    if ms is None:
        return None
    if ms <= 50:
        return STATUS_GOOD
    if ms <= 500:
        return STATUS_WARN
    return STATUS_BAD


# Mini-sector box colours: how far a slice was behind its reference.
BOX_GOOD_MS = 50     # up to this much slower: green
BOX_WARN_MS = 200    # up to this much slower: yellow, beyond it red


def slice_status(delta_ms):
    """Status of one mini-sector against its reference time: purple
    when faster (a new best), green within BOX_GOOD_MS, yellow within
    BOX_WARN_MS, otherwise red. None without a reference."""
    if delta_ms is None:
        return None
    if delta_ms < 0:
        return STATUS_BEST
    if delta_ms <= BOX_GOOD_MS:
        return STATUS_GOOD
    if delta_ms <= BOX_WARN_MS:
        return STATUS_WARN
    return STATUS_BAD
