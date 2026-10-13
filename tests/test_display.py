import pytest

from pitwall_core.display import (
    STATUS_RGBA, format_average, format_current_lap, format_fuel_lap, format_gear, format_laps,
    format_litres, format_speed, format_surplus, format_target,
)
from pitwall_core.fuel import FuelLap
from pitwall_core.laps import EXCLUDED_PIT


def test_format_litres():
    assert format_litres(None) == "--"
    assert format_litres(51.8) == "51.80 L"


def test_format_fuel_lap():
    assert format_fuel_lap(None) == "--"
    assert format_fuel_lap(FuelLap(4, 4.08)) == "4.08 L"
    assert format_fuel_lap(FuelLap(4, 4.31, EXCLUDED_PIT)) == "4.31 L (pit)"


def test_format_average():
    assert format_average(None, 0) == "--"
    assert format_average(4.106, 5) == "4.11 L (5 laps)"


def test_format_laps():
    assert format_laps(None) == "--"
    assert format_laps(12.603) == "12.6"


def test_format_surplus_uses_ascii_signs():
    assert format_surplus(2.3, 4.0) == "+2.30 L (+0.6 laps)"
    assert format_surplus(-4.0, 4.0) == "-4.00 L (-1.0 laps)"
    assert format_surplus(None, 4.0) == "--"


def test_format_target():
    assert format_target(None) == "--"
    assert format_target(3.814) == "3.81 L/lap"


def test_format_current_lap():
    assert format_current_lap(1.73, 0.04) == "1.73 L (+0.04)"
    assert format_current_lap(1.73, -0.04) == "1.73 L (-0.04)"
    assert format_current_lap(1.73, None) == "1.73 L"
    assert format_current_lap(None, 0.04) == "--"


def test_format_speed():
    assert format_speed(None) == "--"
    assert format_speed(187.4) == "187 km/h"


@pytest.mark.parametrize("gear, expected", [(0, "R"), (1, "N"), (2, "1"), (7, "6"), (None, "--")])
def test_format_gear(gear, expected):
    assert format_gear(gear) == expected


def test_every_status_has_a_colour():
    for rgba in STATUS_RGBA.values():
        assert len(rgba) == 4 and all(0.0 <= channel <= 1.0 for channel in rgba)
