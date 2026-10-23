from .base import Driver


class VirtualDriver(Driver):
    """No hardware: the colors only show up in the window's preview."""

    key = "virtual"
    label = "None (preview only)"

    def open(self):
        self.description = "Preview only, no lights connected"

    def send(self, colors):
        pass

    def off(self, count):
        pass
