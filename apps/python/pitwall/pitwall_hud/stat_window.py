"""
stat_window.py — draw a WindowSpec as an AC window: a caption column
and a value column, one row per stat, values coloured by status.

TITLE-BAR ICON
---------------
AC draws the same AC logo (content/gui/inapp_aclogo.png, built into
the game) in every window's title bar, and the Python API can't change
it per window; the app-bar icons in content/gui/icons/ aren't used
there. So the logo is moved out of view and the window's own _ON icon
is drawn in its place as a label background.
"""

import ac

from pitwall_core.display import STATUS_RGBA

FIRST_ROW_Y = 35
ROW_HEIGHT = 24
VALUE_X = 90

# Path relative to the AC install; deploy_app.py puts the icons there.
TITLE_ICON_PATH = "content/gui/icons/{}_ON.png"
TITLE_ICON_POSITION = (5, 3)
TITLE_ICON_SIZE = 26
OFF_SCREEN = -10000

# Row of status boxes under the rows (WindowSpec.boxes).
BOX_HEIGHT = 12
BOX_GAP = 1
BOX_MARGIN = 10
BOX_EMPTY_RGBA = (0.3, 0.3, 0.3, 1.0)


class StatWindow(object):

    def __init__(self, spec):
        self.spec = spec
        self.name = spec.name
        self._window = ac.newApp(spec.name)
        ac.setTitle(self._window, spec.title)
        boxes_y = FIRST_ROW_Y + len(spec.rows) * ROW_HEIGHT
        height = boxes_y + 5 + (BOX_HEIGHT + 5 if spec.boxes is not None else 0)
        ac.setSize(self._window, spec.width, height)
        self._replace_title_icon()

        self._values = {}
        for index, (key, caption) in enumerate(spec.rows):
            y = FIRST_ROW_Y + index * ROW_HEIGHT
            caption_label = ac.addLabel(self._window, caption)
            ac.setPosition(caption_label, 10, y)
            value_label = ac.addLabel(self._window, "--")
            ac.setPosition(value_label, VALUE_X, y)
            self._values[key] = value_label

        self._boxes = []
        if spec.boxes is not None:
            self._add_boxes(boxes_y)

    def _add_boxes(self, y):
        count = self.spec.box_count
        pitch = (self.spec.width - 2 * BOX_MARGIN) // count
        for index in range(count):
            box = ac.addLabel(self._window, "")
            ac.setPosition(box, BOX_MARGIN + index * pitch, y)
            ac.setSize(box, pitch - BOX_GAP, BOX_HEIGHT)
            ac.drawBackground(box, 1)
            ac.setBackgroundOpacity(box, 1)
            self._set_box(box, None)
            self._boxes.append(box)

    @staticmethod
    def _set_box(box, status):
        r, g, b, _ = BOX_EMPTY_RGBA if status is None else STATUS_RGBA[status]
        ac.setBackgroundColor(box, r, g, b)

    def _replace_title_icon(self):
        ac.setIconPosition(self._window, 0, OFF_SCREEN)
        icon = ac.addLabel(self._window, "")
        ac.setPosition(icon, *TITLE_ICON_POSITION)
        ac.setSize(icon, TITLE_ICON_SIZE, TITLE_ICON_SIZE)
        ac.setBackgroundTexture(icon, TITLE_ICON_PATH.format(self.name))

    def render(self, state):
        for key, (text, status) in self.spec.readout(state).items():
            label = self._values[key]
            ac.setText(label, text)
            r, g, b, a = STATUS_RGBA[status]
            ac.setFontColor(label, r, g, b, a)
        if self.spec.boxes is not None:
            for box, status in zip(self._boxes, self.spec.boxes(state)):
                self._set_box(box, status)
