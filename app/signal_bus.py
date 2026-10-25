from app.signal import Signal


class SignalBus:
    activationRequested = Signal()
    exceptionCaught = Signal(str)


signalBus = SignalBus()
