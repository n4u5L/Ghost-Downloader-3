from __future__ import annotations

from bkit import ui

from app.config.cfg import cfg
from app.ui.layout import row
from app.ui.loop import SingleShotTimer
from app.ui.theme import isDark, schemeColor

HANDLE_SIZE = 22
HANDLE_RADIUS = HANDLE_SIZE // 2
INNER_RADIUS = 5
GROOVE_HEIGHT = 4
LABEL_HEIGHT = 24
LABEL_GAP = 4
LABEL_PADDING_H = 8
LABEL_PADDING_V = 6
LABEL_FONT_SIZE = 12
HEIGHT = LABEL_HEIGHT + LABEL_GAP + HANDLE_SIZE


def parseTimeInput(value: str) -> int:
    value = value.strip()
    if not value:
        return 0
    parts = value.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        return int(value)
    except ValueError:
        return 0


def toTimeText(value: int) -> str:
    minutes, seconds = divmod(value, 60)
    return f"{minutes}:{seconds:02d}"


def matchPosition(rect, x, y):
    left, top, right, bottom = rect
    return left <= x <= right and top <= y <= bottom


class RangeSlider(ui.Node):
    """The Qt range slider's geometry and input, composed with native text nodes."""

    def __init__(self, minimum, maximum, start, end, onChanged, onHover, previewAnchor, post,
                 *, formatter=toTimeText, parser=parseTimeInput):
        super().__init__()
        self.pointer_input = True
        self.clip_to_bounds = True
        self._minimum, self._maximum = minimum, max(minimum, maximum)
        self._startValue = max(minimum, min(start, self._maximum))
        self._endValue = max(self._startValue, min(end, self._maximum))
        self._onChanged, self._onHover = onChanged, onHover
        self._formatter, self._parser = formatter, parser
        self._previewAnchor = previewAnchor
        self._previewX = 0
        self._dragging = self._editingHandle = None
        self._lineEdit = self._editBox = None
        self._hasEditFocus = False
        self._editFocusTimer = SingleShotTimer(post, 0.03, self._onEditFocusChanged)
        self._startLabel = ui.Text(formatter(self._startValue), max_lines=1, soft_wrap=False)
        self._endLabel = ui.Text(formatter(self._endValue), max_lines=1, soft_wrap=False)
        for label in (self._startLabel, self._endLabel):
            label.set_text_style(font_size=LABEL_FONT_SIZE, line_height=14)
            self.append_child(label)
        self.append_child(previewAnchor)
        self._onThemeChanged()
        cfg.themeMode.valueChanged.connect(self._onThemeChanged)

    def on_measure(self, constraints):
        for label in (self._startLabel, self._endLabel):
            label.measure(ui.Constraints(0, float("inf"), 0, float("inf")))
        self._previewAnchor.measure(ui.Constraints.fixed(self.dp(1), self.dp(1)))
        if self._editBox is not None:
            self._editBox.measure(ui.Constraints.fixed(self.dp(56), self.dp(LABEL_HEIGHT)))
        width = constraints.max_width if constraints.has_bounded_width else self.dp(340)
        return constraints.constrain(width, self.dp(HEIGHT))

    def on_place(self):
        for label, rect in zip((self._startLabel, self._endLabel), self._buildLabelRects()):
            label.place(rect[0] + self.dp(LABEL_PADDING_H), rect[1] + self.dp(LABEL_PADDING_V))
        width, _ = self.measured_size
        self._previewAnchor.place(max(0, min(width - self.dp(1), self._previewX)), 0)
        if self._editBox is not None:
            self._editBox.place(self._editX(), 0)

    def _toPixelX(self, value):
        span = self._maximum - self._minimum
        if span <= 0:
            return self.dp(HANDLE_RADIUS)
        width, _ = self.measured_size
        return self.dp(HANDLE_RADIUS) + (value - self._minimum) / span * (width - self.dp(HANDLE_SIZE))

    def _toValue(self, x):
        width, _ = self.measured_size
        length = width - self.dp(HANDLE_SIZE)
        if length <= 0:
            return self._minimum
        ratio = max(0, min(1, (x - self.dp(HANDLE_RADIUS)) / length))
        return self._minimum + round(ratio * (self._maximum - self._minimum))

    def _buildLabelRects(self):
        width, _ = self.measured_size
        startX, endX = self._toPixelX(self._startValue), self._toPixelX(self._endValue)
        startWidth, startHeight = self._startLabel.measured_size
        endWidth, endHeight = self._endLabel.measured_size
        startWidth += self.dp(LABEL_PADDING_H * 2)
        endWidth += self.dp(LABEL_PADDING_H * 2)
        height = max(startHeight, endHeight) + self.dp(LABEL_PADDING_V * 2)
        top = self.dp(LABEL_HEIGHT) - height
        startLeft, endLeft = startX - startWidth / 2, endX - endWidth / 2
        if startLeft + startWidth + self.dp(2) > endLeft:
            mid = (startX + endX) / 2
            startLeft, endLeft = mid - startWidth - self.dp(1), mid + self.dp(1)
        startLeft = max(0, min(width - startWidth, startLeft))
        endLeft = max(0, min(width - endWidth, endLeft))
        return ((startLeft, top, startLeft + startWidth, self.dp(LABEL_HEIGHT)),
                (endLeft, top, endLeft + endWidth, self.dp(LABEL_HEIGHT)))

    def on_draw(self, canvas):
        width, _ = self.measured_size
        startX, endX = self._toPixelX(self._startValue), self._toPixelX(self._endValue)
        centerY = self.dp(LABEL_HEIGHT + LABEL_GAP + HANDLE_RADIUS)
        top, bottom = centerY - self.dp(GROOVE_HEIGHT / 2), centerY + self.dp(GROOVE_HEIGHT / 2)
        canvas.draw_round_rect(self.dp(HANDLE_RADIUS), top, max(self.dp(HANDLE_RADIUS), width - self.dp(HANDLE_RADIUS)),
            bottom, self.dp(2), self.dp(2), 0x73FFFFFF if self._dark else 0x64000000)
        if endX > startX:
            canvas.draw_round_rect(startX, top, endX, bottom, self.dp(2), self.dp(2), self._accent)
        for x in (startX, endX):
            canvas.draw_circle(x, centerY, self.dp(HANDLE_RADIUS), 0xFF454545 if self._dark else 0xFFFFFFFF)
            canvas.draw_circle(x, centerY, self.dp(HANDLE_RADIUS),
                0x5A000000 if self._dark else 0x19000000, stroke_width=self.dp(1))
            canvas.draw_circle(x, centerY, self.dp(INNER_RADIUS), self._accent)
        for rect in self._buildLabelRects():
            canvas.draw_round_rect(*rect, self.dp(4), self.dp(4), 0xFF323232 if self._dark else 0xFFF9F9F9)
            canvas.draw_round_rect(*rect, self.dp(4), self.dp(4),
                0x0FFFFFFF if self._dark else 0x19000000, stroke_width=self.dp(1))

    def on_pointer_event(self, event, pass_, bounds):
        if pass_ == ui.PointerEventPass.INITIAL:
            if event.type == ui.PointerEventType.EXIT:
                self._onHover(None)
            elif event.type in (ui.PointerEventType.ENTER, ui.PointerEventType.MOVE) and event.changes:
                x, _ = event.changes[0].position
                if x != self._previewX:
                    self._previewX = x
                    self.request_relayout()
                self._onHover(self._toValue(x))
            return
        if pass_ != ui.PointerEventPass.MAIN:
            return
        if not event.changes:
            return
        change = event.changes[0]
        x, y = change.position
        if event.type == ui.PointerEventType.PRESS:
            if change.is_consumed or not event.buttons & ui.PointerButtons.PRIMARY:
                return
            if self._editBox is not None and matchPosition(
                    (self._editX(), 0, self._editX() + self.dp(56), self.dp(LABEL_HEIGHT)), x, y):
                self._lineEdit.request_focus()
                change.consume()
                return
            if y < self.dp(LABEL_HEIGHT):
                startRect, endRect = self._buildLabelRects()
                if matchPosition(endRect, x, y):
                    self._startInlineEdit("end")
                    change.consume()
                elif matchPosition(startRect, x, y):
                    self._startInlineEdit("start")
                    change.consume()
                return
            startX, endX = self._toPixelX(self._startValue), self._toPixelX(self._endValue)
            self._dragging = "start" if abs(x - startX) < abs(x - endX) else "end"
            self._updateDrag(x)
            change.consume()
        elif event.type == ui.PointerEventType.MOVE:
            if self._dragging:
                self._updateDrag(x)
                change.consume()
        elif event.type == ui.PointerEventType.RELEASE and not event.buttons & ui.PointerButtons.PRIMARY:
            if self._dragging:
                self._dragging = None
                change.consume()

    def on_cancel_pointer_input(self):
        self._dragging = None
        self._onHover(None)

    def _updateDrag(self, x):
        value = self._toValue(x)
        if self._dragging == "start":
            value = max(self._minimum, min(value, self._endValue))
            if value == self._startValue:
                return
            self._startValue = value
        else:
            value = max(self._startValue, min(value, self._maximum))
            if value == self._endValue:
                return
            self._endValue = value
        self._updateLabels()
        self._onChanged(self._startValue, self._endValue)

    def _editX(self):
        width, _ = self.measured_size
        value = self._startValue if self._editingHandle == "start" else self._endValue
        return max(0, min(width - self.dp(56), self._toPixelX(value) - self.dp(28)))

    def _startInlineEdit(self, handle):
        self.flush()
        self._editingHandle = handle
        value = self._startValue if handle == "start" else self._endValue
        self._lineEdit = ui.BasicTextField(ui.TextFieldState(self._formatter(value)))
        self._lineEdit.set_line_limits(single_line=True)
        self._lineEdit.set_text_style(font_size=LABEL_FONT_SIZE, line_height=14)
        self._lineEdit.set_keyboard_options(ime_action=ui.ImeAction.DONE)
        self._lineEdit.on_keyboard_action = self.flush
        self._editBox = ui.Box()
        self._editBox.set_padding(4, 0)
        self._editBox.set_corner_radius(4)
        self._editBox.set_content_alignment(ui.Alignment.START, ui.Alignment.CENTER)
        self._editBox.append_child(row(self._lineEdit, flex=0))
        self.append_child(self._editBox)
        self._onThemeChanged()
        self._hasEditFocus = self._lineEdit.request_focus()
        self._lineEdit.state.edit(lambda buffer: buffer.select_all())
        self._editFocusTimer.start()

    def _onEditFocusChanged(self):
        if self._lineEdit is None:
            return
        if not self.is_attached:
            return
        if not self._hasEditFocus:
            if self._lineEdit.is_placed:
                self._hasEditFocus = self._lineEdit.request_focus()
        elif not self._lineEdit.has_focus:
            self.flush()
            return
        self._editFocusTimer.start()

    def _removeInlineEdit(self):
        self._editFocusTimer.stop()
        box = self._editBox
        self._lineEdit = self._editBox = self._editingHandle = None
        self._hasEditFocus = False
        self.remove_child(self.children.index(box))

    def flush(self):
        if self._lineEdit is None:
            return
        value, handle = self._lineEdit.state.text, self._editingHandle
        self._removeInlineEdit()
        try:
            value = self._parser(value)
        except (ValueError, TypeError):
            self.request_draw()
            return
        if handle == "start":
            self._startValue = max(self._minimum, min(value, self._endValue))
        else:
            self._endValue = max(self._startValue, min(value, self._maximum))
        self._updateLabels()
        self._onChanged(self._startValue, self._endValue)

    def _updateLabels(self):
        self._startLabel.text = self._formatter(self._startValue)
        self._endLabel.text = self._formatter(self._endValue)
        self.request_remeasure()
        self.request_draw()

    def _onThemeChanged(self, *_):
        self._dark, self._accent = isDark(), schemeColor("primary")
        color = 0xFFFFFFFF if self._dark else 0xFF000000
        self._startLabel.set_color(color)
        self._endLabel.set_color(color)
        if self._lineEdit is not None:
            self._lineEdit.set_text_color(color)
            self._lineEdit.set_cursor_color(self._accent)
            self._editBox.set_background(0xFF323232 if self._dark else 0xFFF9F9F9)
            self._editBox.set_border(1, self._accent)
        self.request_draw()

    def on_detach(self):
        self._dragging = None
        self._editFocusTimer.stop()
        self._onHover(None)

    def on_attach(self):
        if self._lineEdit is not None:
            self._hasEditFocus = False
            self._editFocusTimer.start()

    def dispose(self):
        cfg.themeMode.valueChanged.disconnect(self._onThemeChanged)
        self._editFocusTimer.stop()
        if self._lineEdit is not None:
            self._removeInlineEdit()
        self._dragging = None
