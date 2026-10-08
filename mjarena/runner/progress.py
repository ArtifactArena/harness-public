"""Live terminal progress without copying redraws into the run's log file."""
import multiprocessing
import os
import sys
import threading


class TerminalStream:
    def __init__(self, stream):
        self.stream = stream

    def write(self, text):
        write = getattr(self.stream, "write_ephemeral", self.stream.write)
        return write(text)

    def flush(self):
        self.stream.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)


def match_progress_options(seed, label=None):
    # Pool workers share the terminal. Their coordinator owns the dashboard.
    main = (multiprocessing.current_process().name == "MainProcess"
            and threading.current_thread() is threading.main_thread())
    mode = os.environ.get("ARENA_PROGRESS", "auto")
    enabled = main and (mode == "1" or (mode != "0" and sys.stderr.isatty()))
    return dict(
        disable=not enabled, file=TerminalStream(sys.stderr),
        desc=label or f"Match seed {seed}", leave=True, dynamic_ncols=True,
        mininterval=0.5, unit="step",
        bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} "
                   "[elapsed {elapsed} | ETA {remaining} | {rate_fmt}]{postfix}",
    )
