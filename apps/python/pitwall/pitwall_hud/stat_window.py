"""
stat_window.py — draw a WindowSpec as an AC window: a caption column
and a value column, one row per stat, values coloured by status.
"""

import ac

from pitwall_core.display import STATUS_RGBA

FIRST_ROW_Y = 35
ROW_HEIGHT = 24
VALUE_X = 90


class StatWindow(object):

    def __init__(self, spec):
        self.spec = spec
        self.name = spec.name
        self._window = ac.newApp(spec.name)
        ac.setTitle(self._window, spec.title)
        ac.setSize(self._window, spec.width, FIRST_ROW_Y + len(spec.rows) * ROW_HEIGHT + 5)

        self._values = {}
        for index, (key, caption) in enumerate(spec.rows):
            y = FIRST_ROW_Y + index * ROW_HEIGHT
            caption_label = ac.addLabel(self._window, caption)
            ac.setPosition(caption_label, 10, y)
            value_label = ac.addLabel(self._window, "--")
            ac.setPosition(value_label, VALUE_X, y)
            self._values[key] = value_label

    def render(self, state):
        for key, (text, status) in self.spec.readout(state).items():
            label = self._values[key]
            ac.setText(label, text)
            r, g, b, a = STATUS_RGBA[status]
            ac.setFontColor(label, r, g, b, a)
