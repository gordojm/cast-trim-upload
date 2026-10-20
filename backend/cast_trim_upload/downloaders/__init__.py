"""Section downloaders. Each returns the path of an audio file covering [start, end]."""

from collections.abc import Callable
from threading import Event

from ..messages import E_CANCELLED, AppError
from ..models import Message

ProgressFn = Callable[[float | None, Message], None]


class DownloadError(AppError):
    pass


class DownloadCancelled(DownloadError):
    def __init__(self) -> None:
        super().__init__(E_CANCELLED)


def check_cancel(cancel: Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise DownloadCancelled()
