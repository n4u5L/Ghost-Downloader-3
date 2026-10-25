"""bkit 的 Row/Column 没有权重：这里补上「一个子节点吃掉剩余空间」的布局，以及常用的小件。"""
from __future__ import annotations

from collections.abc import Callable

from bkit import ui

INF = float("inf")
# 按下到松开移动超过它（dp）就算拖动，不算点击
CLICK_SLOP = 8


class Slot(ui.Node):
    """让唯一的子节点填满自身；约束无界时取 fallback 尺寸（dp）。"""

    def __init__(self, child: ui.Node | None = None, fallback: tuple[float, float] = (960, 540)) -> None:
        super().__init__()
        self._fallback = fallback
        if child is not None:
            self.append_child(child)

    def setChild(self, child: ui.Node | None) -> None:
        while self.children:
            self.remove_child(0)
        if child is not None:
            self.append_child(child)

    def on_measure(self, constraints: ui.Constraints, /) -> tuple[float, float]:
        width = constraints.max_width if constraints.has_bounded_width else self.dp(self._fallback[0])
        height = constraints.max_height if constraints.has_bounded_height else self.dp(self._fallback[1])
        for child in self.children:
            child.measure(ui.Constraints.fixed(width, height))
        return constraints.constrain(width, height)

    def on_place(self) -> None:
        for child in self.children:
            child.place(0, 0)


class Flex(ui.Node):
    """沿主轴排列子节点；下标为 flex 的子节点得到其余子节点留下的空间。

    isMainFilled 时 flex 子节点被撑满剩余空间，自身也占满主轴；否则 flex 子节点最多取剩余空间，
    自身按内容收缩，用于「正文可滚动、按钮行固定」的对话框。
    isCrossFilled 时每个子节点在交叉轴上被撑满，否则居中。
    """

    def __init__(self, *children: ui.Node, isVertical: bool = False, flex: int = -1, spacing: float = 0.0,
                 isCrossFilled: bool = False, isMainFilled: bool = True) -> None:
        super().__init__()
        self._isVertical = isVertical
        self._flex = flex
        self._spacing = spacing
        self._isCrossFilled = isCrossFilled
        self._isMainFilled = isMainFilled
        for child in children:
            self.append_child(child)

    @property
    def flex(self) -> int:
        return self._flex

    def setFlex(self, index: int) -> None:
        self._flex = index
        self.request_remeasure()

    def on_measure(self, constraints: ui.Constraints, /) -> tuple[float, float]:
        children = self.children
        if self._isVertical:
            maxMain, maxCross = constraints.max_height, constraints.max_width
        else:
            maxMain, maxCross = constraints.max_width, constraints.max_height
        isMainBounded = maxMain != INF
        isCrossBounded = maxCross != INF
        minCross = maxCross if self._isCrossFilled and isCrossBounded else 0.0
        hasFlex = 0 <= self._flex < len(children)

        used = self.dp(self._spacing) * max(0, len(children) - 1)
        cross = 0.0
        for index, child in enumerate(children):
            if index == self._flex:
                continue
            available = max(0.0, maxMain - used) if isMainBounded else INF
            main, childCross = self._measureChild(child, 0.0, available, minCross, maxCross)
            used += main
            cross = max(cross, childCross)

        if hasFlex:
            if isMainBounded:
                remaining = max(0.0, maxMain - used)
                minMain = remaining if self._isMainFilled else 0.0
                main, childCross = self._measureChild(children[self._flex], minMain, remaining, minCross, maxCross)
            else:
                main, childCross = self._measureChild(children[self._flex], 0.0, INF, minCross, maxCross)
            used += main
            cross = max(cross, childCross)

        main = maxMain if isMainBounded and hasFlex and self._isMainFilled else used
        cross = maxCross if self._isCrossFilled and isCrossBounded else cross
        if self._isVertical:
            return constraints.constrain(cross, main)
        return constraints.constrain(main, cross)

    def _measureChild(self, child: ui.Node, minMain: float, maxMain: float,
                      minCross: float, maxCross: float) -> tuple[float, float]:
        if self._isVertical:
            width, height = child.measure(ui.Constraints(minCross, maxCross, minMain, maxMain))
            return height, width
        width, height = child.measure(ui.Constraints(minMain, maxMain, minCross, maxCross))
        return width, height

    def on_place(self) -> None:
        width, height = self.measured_size
        spacing = self.dp(self._spacing)
        position = 0.0
        for child in self.children:
            childWidth, childHeight = child.measured_size
            if self._isVertical:
                child.place((width - childWidth) / 2, position)
                position += childHeight + spacing
            else:
                child.place(position, (height - childHeight) / 2)
                position += childWidth + spacing


class EqualRow(ui.Node):
    """子节点等宽排成一行、撑满宽度，对应 Qt 对话框底部各按钮同宽的按钮栏。"""

    def __init__(self, *children: ui.Node, spacing: float = 0.0) -> None:
        super().__init__()
        self._spacing = spacing
        for child in children:
            self.append_child(child)

    def on_measure(self, constraints: ui.Constraints, /) -> tuple[float, float]:
        children = self.children
        if not children:
            return constraints.constrain(0.0, 0.0)
        spacing = self.dp(self._spacing) * (len(children) - 1)
        if constraints.has_bounded_width:
            width = max(0.0, (constraints.max_width - spacing) / len(children))
            childConstraints = ui.Constraints(width, width, 0.0, constraints.max_height)
        else:
            childConstraints = ui.Constraints(0.0, INF, 0.0, constraints.max_height)
        sizes = [child.measure(childConstraints) for child in children]
        total = sum(width for width, _ in sizes) + spacing
        return constraints.constrain(total, max(height for _, height in sizes))

    def on_place(self) -> None:
        _, height = self.measured_size
        spacing = self.dp(self._spacing)
        position = 0.0
        for child in self.children:
            childWidth, childHeight = child.measured_size
            child.place(position, (height - childHeight) / 2)
            position += childWidth + spacing


class SecondaryClickArea(ui.Node):
    """把子节点上的右键点击交给 onClicked(x, y)，坐标是自身的像素；左键照常传给子节点。"""

    def __init__(self, child: ui.Node, onClicked: Callable[[float, float], object]) -> None:
        super().__init__()
        self._onClicked = onClicked
        self._isPressed = False
        self.pointer_input = True
        self.append_child(child)

    def on_pointer_event(self, event: ui.PointerEvent, pass_: ui.PointerEventPass,
                         bounds: tuple[float, float], /) -> None:
        # 在子节点之前截下右键，免得按钮把它当作点击
        if pass_ != ui.PointerEventPass.INITIAL or not event.changes:
            return
        change = event.changes[0]
        if event.type == ui.PointerEventType.PRESS and event.buttons & ui.PointerButtons.SECONDARY:
            self._isPressed = True
            change.consume()
        elif event.type == ui.PointerEventType.RELEASE and self._isPressed:
            self._isPressed = False
            change.consume()
            self._onClicked(*change.position)


class ClickArea(ui.Node):
    """子节点上没被按钮等消费的左键点击交给 onClicked，对应 Qt 里可点击的卡片和标题行。"""

    def __init__(self, child: ui.Node, onClicked: Callable[[], object]) -> None:
        super().__init__()
        self._onClicked = onClicked
        self._isPressed = False
        self._pressPosition = (0.0, 0.0)
        self.pointer_input = True
        self.append_child(child)

    def on_pointer_event(self, event: ui.PointerEvent, pass_: ui.PointerEventPass,
                         bounds: tuple[float, float], /) -> None:
        # MAIN 阶段子节点先处理：按钮消费过的点击不算这里的
        if pass_ != ui.PointerEventPass.MAIN or not event.changes:
            return
        change = event.changes[0]
        if event.type == ui.PointerEventType.PRESS:
            self._isPressed = not change.is_consumed and bool(event.buttons & ui.PointerButtons.PRIMARY)
            self._pressPosition = change.position
        elif event.type == ui.PointerEventType.RELEASE and self._isPressed:
            self._isPressed = False
            if not change.is_consumed and isClick(change.position, self._pressPosition, self.density):
                change.consume()
                self._onClicked()


def column(*children: ui.Node, spacing: float = 0.0, flex: int = -1, isCrossFilled: bool = True,
           isMainFilled: bool = True) -> Flex:
    return Flex(*children, isVertical=True, flex=flex, spacing=spacing, isCrossFilled=isCrossFilled,
                isMainFilled=isMainFilled)


def row(*children: ui.Node, spacing: float = 0.0, flex: int = -1) -> Flex:
    return Flex(*children, flex=flex, spacing=spacing)


def overlay(content: ui.Node, floating: ui.Node, horizontal: ui.Alignment, vertical: ui.Alignment) -> ui.Box:
    """content 填满，floating 按对齐方式浮在它上面，对应 Qt 里浮在父控件上的 InfoBar、CommandBar。"""
    box = ui.Box()
    box.set_content_alignment(horizontal, vertical)
    box.append_child(content)
    box.append_child(floating)
    return box


def text(value: str = "", *, fontSize: float = 14, fontWeight: int = 400, maxLines: int = 1) -> ui.Text:
    node = ui.Text(value, max_lines=maxLines, overflow=ui.TextOverflow.ELLIPSIS)
    node.set_text_style(font_size=fontSize, line_height=fontSize * 1.4, font_weight=fontWeight)
    return node


def checkBox(label: str, isChecked: bool = False) -> tuple[Flex, ui.Checkbox]:
    """带文字的复选框，对应 qfluentwidgets 的 CheckBox(text)。返回放进布局的行和复选框本身。"""
    box = ui.Checkbox(isChecked)
    box.on_checked_change = lambda checked: setattr(box, "checked", checked)
    return row(box, text(label), spacing=4), box


def isClick(position: tuple[float, float], pressPosition: tuple[float, float], density: float) -> bool:
    return abs(position[0] - pressPosition[0]) + abs(position[1] - pressPosition[1]) <= CLICK_SLOP * density
