"""Smoke test for the in-game wiring: load apps/python/pitwall/pitwall.py
with stand-in `ac` / `acsys` modules and fake shared memory, then run
the acMain / acUpdate / acShutdown lifecycle AC would.

It runs on modern Python, so it can't prove 3.3 compatibility
(test_py33_compat does that), but it catches broken imports, window
setup and the per-frame loop without starting the game.
"""

import importlib.util
import os
import sys
import types

import pytest

from conftest import REPO_ROOT

APP_PATH = os.path.join(REPO_ROOT, "apps", "python", "pitwall", "pitwall.py")


class FakeAC(object):
    """Records what the app draws. Labels are ints, like AC's ids."""

    def __init__(self, car_state):
        self.car_state = car_state
        self.windows = {}
        self.texts = {}
        self.colours = {}
        self.textures = {}
        self.icon_positions = {}
        self.backgrounds = {}
        self.box_colours = {}
        self.logs = []
        self._next_id = 0

    def _new_id(self):
        self._next_id += 1
        return self._next_id

    def newApp(self, name):
        window = self._new_id()
        self.windows[name] = window
        return window

    def addLabel(self, window, text):
        label = self._new_id()
        self.texts[label] = text
        return label

    def setText(self, label, text):
        self.texts[label] = text

    def setFontColor(self, label, r, g, b, a):
        self.colours[label] = (r, g, b, a)

    def getCarState(self, car, field):
        return self.car_state[field]

    def isCarInPitline(self, car):
        return 0

    def log(self, message):
        self.logs.append(message)

    def setBackgroundTexture(self, control, path):
        self.textures[control] = path

    def setIconPosition(self, window, x, y):
        self.icon_positions[window] = (x, y)

    def drawBackground(self, control, flag):
        self.backgrounds[control] = flag

    def setBackgroundOpacity(self, control, opacity):
        pass

    def setBackgroundColor(self, control, r, g, b):
        self.box_colours[control] = (r, g, b)

    def setTitle(self, *args):
        pass

    def setSize(self, *args):
        pass

    def setPosition(self, *args):
        pass


class FakeBlock(object):
    def __init__(self, values):
        self.values = values

    def get(self, name):
        return self.values[name]

    def close(self):
        pass


class FakeMemory(object):
    def __init__(self):
        self.physics = FakeBlock({"fuel": 60.0})
        self.graphics = FakeBlock({"session": 2, "numberOfLaps": 20, "sessionTimeLeft": 0.0})
        self.static = FakeBlock({"isTimedRace": 0, "hasExtraLap": 0})

    def close(self):
        pass


CS_FIELDS = ("LapCount", "NormalizedSplinePosition", "LapTime", "SpeedKMH", "Gear")


@pytest.fixture
def app(monkeypatch):
    acsys = types.ModuleType("acsys")
    acsys.CS = types.SimpleNamespace(**{name: name for name in CS_FIELDS})
    fake_ac = FakeAC({"LapCount": 2, "NormalizedSplinePosition": 0.4, "LapTime": 50000,
                      "SpeedKMH": 120.0, "Gear": 4})
    monkeypatch.setitem(sys.modules, "ac", fake_ac)
    monkeypatch.setitem(sys.modules, "acsys", acsys)

    spec = importlib.util.spec_from_file_location("pitwall", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "pitwall", module)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "SharedMemory", FakeMemory)
    yield module, fake_ac
    for name in [name for name in sys.modules if name.startswith("pitwall_hud")]:
        del sys.modules[name]


def label_texts(fake_ac):
    return set(fake_ac.texts.values())


def test_app_lifecycle_draws_every_window(app):
    module, fake_ac = app
    assert module.acMain("1.16") == "pitwall"
    assert set(fake_ac.windows) == {"pitwall_fuel", "pitwall_car", "pitwall_time"}

    for _ in range(3):
        module.acUpdate(0.016)

    texts = label_texts(fake_ac)
    assert "60.00 L" in texts       # fuel window: tank
    assert "120 km/h" in texts      # car window: speed
    assert "3" in texts             # car window: gear 4 = third
    assert "50.000" in texts        # time window: lap timer
    assert any(message.startswith("pitwall: session=2 laps=20") for message in fake_ac.logs)
    assert not module.failed_windows

    module.acShutdown()


def test_time_window_draws_a_box_per_mini_sector(app):
    from pitwall_core.sectors import MINI_SECTORS
    module, fake_ac = app
    module.acMain("1.16")
    for _ in range(3):
        module.acUpdate(0.016)
    assert len(fake_ac.backgrounds) == MINI_SECTORS
    assert len(fake_ac.box_colours) == MINI_SECTORS
    assert not module.failed_windows


def test_each_window_swaps_the_ac_logo_for_its_own_icon(app):
    module, fake_ac = app
    module.acMain("1.16")

    # AC's logo is moved out of view in every window...
    assert set(fake_ac.icon_positions) == set(fake_ac.windows.values())
    assert all(y < -1000 for _, y in fake_ac.icon_positions.values())
    # ...and each window draws its own icon, from a file deploy installs.
    textures = sorted(fake_ac.textures.values())
    assert textures == ["content/gui/icons/pitwall_car_ON.png", "content/gui/icons/pitwall_fuel_ON.png",
                        "content/gui/icons/pitwall_time_ON.png"]
    for path in textures:
        assert os.path.isfile(os.path.join(REPO_ROOT, path))


def test_a_failing_window_is_logged_once_and_the_others_keep_drawing(app, monkeypatch):
    module, fake_ac = app
    module.acMain("1.16")

    def broken(state):
        raise RuntimeError("boom")

    monkeypatch.setattr(module.windows[0].spec, "readout", broken)
    for _ in range(3):
        module.acUpdate(0.016)

    assert module.failed_windows == {"pitwall_fuel"}
    assert sum("window pitwall_fuel failed" in message for message in fake_ac.logs) == 1
    assert "120 km/h" in label_texts(fake_ac)
