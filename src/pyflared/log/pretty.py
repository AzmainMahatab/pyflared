import io

from rich.console import Console


class Pretty:
    """
    Mark a dictionary/list/object to be pretty-printed by Rich
    before being sent to Loguru.
    """

    def __init__(self, data):
        self.data = data

    def __str__(self):
        # Create a private memory buffer for this specific log entry
        buf = io.StringIO()
        # force_terminal=True ensures ANSI codes are generated
        c = Console(file=buf, force_terminal=True)
        c.print(self.data)
        return buf.getvalue().strip()
