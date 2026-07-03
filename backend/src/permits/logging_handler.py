import logging

from tqdm import tqdm


class TqdmLoggingHandler(logging.StreamHandler):
    """Emit log records through ``tqdm.write`` so they don't land on the same line
    as a live progress bar. ``tqdm.write`` clears the bar, prints the record on its
    own line (with a trailing newline), then redraws the bar below it."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            tqdm.write(self.format(record), file=self.stream)
            self.flush()
        except Exception:
            self.handleError(record)
