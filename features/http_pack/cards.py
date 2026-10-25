from bkit import ui

from app.models.task import TaskStatus
from app.ui.cards.task_cards import TaskCard
from app.ui.theme import schemeColor, statusColor


class SegmentedProgressBar(ui.Node):
    def __init__(self, task, uiLoop):
        super().__init__()
        self.task = task
        self._uiLoop = uiLoop
        self._timer = None
        self._shown = {}

    def on_measure(self, constraints):
        width = constraints.max_width if constraints.has_bounded_width else self.dp(4096)
        return constraints.constrain(width, self.dp(4))

    def on_attach(self):
        super().on_attach()
        self._tick()

    def on_detach(self):
        if self._timer:
            self._timer.cancel()
            self._timer = None
        super().on_detach()

    def _tick(self):
        self._timer = None
        workers = [worker for step in self.task.steps for worker in list(getattr(step, "subworkers", ()))]
        fresh = not self._shown
        shown = {}
        for worker in workers:
            previous = self._shown.get(worker.start, worker.position if fresh else worker.start)
            shown[worker.start] = previous + (worker.position - previous) * 0.25
        self._shown = shown
        self.request_draw()
        if self.is_attached and self.task.status == TaskStatus.RUNNING:
            self._timer = self._uiLoop.post(self._tick, 0.016)

    def refresh(self):
        if self.is_attached and self._timer is None:
            self._tick()
        else:
            self.request_draw()

    def on_draw(self, canvas):
        super().on_draw(canvas)
        width, height = self.measured_size
        total = max(self.task.fileSize, 1)
        color = statusColor("error") if self.task.status == TaskStatus.FAILED else (
            statusColor("warning") if self.task.status == TaskStatus.PAUSED else schemeColor("primary"))
        spans = list(self._shown.items())
        if not spans:
            spans = [(0, self.task.currentSnapshot()[2])]
        for start, end in spans:
            if end > start:
                canvas.draw_rect(width * start / total, 0, min(width, width * end / total), height, color)


class HttpTaskCard(TaskCard):
    def __init__(self, *args, uiLoop):
        self._uiLoop = uiLoop
        super().__init__(*args)

    def _refreshProgress(self, task, progress):
        if task.status == TaskStatus.COMPLETED or task.fileSize <= 0:
            return super()._refreshProgress(task, progress)
        if self._progressKind != "segments":
            while self.progressSlot.children:
                self.progressSlot.remove_child(0)
            self.progressBar = SegmentedProgressBar(task, self._uiLoop)
            self.progressSlot.append_child(self.progressBar)
            self._progressKind = "segments"
        self.progressBar.refresh()
