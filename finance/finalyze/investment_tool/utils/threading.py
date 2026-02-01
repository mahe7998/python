"""Thread workers for background data fetching."""

from typing import Any, Callable, Optional
from dataclasses import dataclass

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from loguru import logger


@dataclass
class WorkerResult:
    """Result from a worker task."""
    success: bool
    data: Any = None
    error: Optional[Exception] = None


class WorkerSignals(QObject):
    """Signals for worker communication."""
    started = Signal()
    finished = Signal(object)
    error = Signal(Exception)
    progress = Signal(int)


class Worker(QRunnable):
    """Worker thread for background tasks."""

    def __init__(
        self,
        fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self._is_cancelled = False

    def cancel(self) -> None:
        """Request cancellation of the worker."""
        self._is_cancelled = True

    @property
    def is_cancelled(self) -> bool:
        """Check if worker has been cancelled."""
        return self._is_cancelled

    @Slot()
    def run(self) -> None:
        """Execute the worker function."""
        self.signals.started.emit()

        try:
            if self._is_cancelled:
                return

            result = self.fn(*self.args, **self.kwargs)
            self.signals.finished.emit(
                WorkerResult(success=True, data=result)
            )

        except Exception as e:
            logger.exception(f"Worker error: {e}")
            self.signals.error.emit(e)
            self.signals.finished.emit(
                WorkerResult(success=False, error=e)
            )


class DataFetchWorker(Worker):
    """Specialized worker for fetching data."""

    def __init__(
        self,
        fetch_fn: Callable[..., Any],
        ticker: str,
        *args: Any,
        **kwargs: Any,
    ):
        super().__init__(fetch_fn, *args, **kwargs)
        self.ticker = ticker


class ThreadManager:
    """Manages thread pool for background tasks."""

    def __init__(self, max_threads: Optional[int] = None):
        self.pool = QThreadPool.globalInstance()
        if max_threads:
            self.pool.setMaxThreadCount(max_threads)
        self._active_workers: dict[str, Worker] = {}

    @property
    def max_threads(self) -> int:
        """Get maximum thread count."""
        return self.pool.maxThreadCount()

    @property
    def active_threads(self) -> int:
        """Get number of active threads."""
        return self.pool.activeThreadCount()

    def submit(
        self,
        fn: Callable[..., Any],
        *args: Any,
        on_finished: Optional[Callable[[WorkerResult], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_progress: Optional[Callable[[int], None]] = None,
        worker_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Worker:
        """
        Submit a function to run in the thread pool.

        Args:
            fn: Function to execute
            *args: Positional arguments for fn
            on_finished: Callback when finished
            on_error: Callback on error
            on_progress: Callback for progress updates
            worker_id: Optional ID to track/cancel the worker
            **kwargs: Keyword arguments for fn

        Returns:
            Worker instance
        """
        worker = Worker(fn, *args, **kwargs)

        if on_finished:
            worker.signals.finished.connect(on_finished)
        if on_error:
            worker.signals.error.connect(on_error)
        if on_progress:
            worker.signals.progress.connect(on_progress)

        if worker_id:
            if worker_id in self._active_workers:
                self._active_workers[worker_id].cancel()
            self._active_workers[worker_id] = worker

            def cleanup(result: WorkerResult) -> None:
                if worker_id in self._active_workers:
                    del self._active_workers[worker_id]

            worker.signals.finished.connect(cleanup)

        self.pool.start(worker)
        return worker

    def submit_data_fetch(
        self,
        fetch_fn: Callable[..., Any],
        ticker: str,
        *args: Any,
        on_finished: Optional[Callable[[WorkerResult], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        **kwargs: Any,
    ) -> DataFetchWorker:
        """
        Submit a data fetch operation.

        Args:
            fetch_fn: Data fetch function
            ticker: Stock ticker
            *args: Additional arguments
            on_finished: Callback when finished
            on_error: Callback on error
            **kwargs: Keyword arguments

        Returns:
            DataFetchWorker instance
        """
        worker = DataFetchWorker(fetch_fn, ticker, *args, **kwargs)

        if on_finished:
            worker.signals.finished.connect(on_finished)
        if on_error:
            worker.signals.error.connect(on_error)

        worker_id = f"fetch:{ticker}"
        if worker_id in self._active_workers:
            self._active_workers[worker_id].cancel()
        self._active_workers[worker_id] = worker

        def cleanup(result: WorkerResult) -> None:
            if worker_id in self._active_workers:
                del self._active_workers[worker_id]

        worker.signals.finished.connect(cleanup)

        self.pool.start(worker)
        return worker

    def cancel(self, worker_id: str) -> bool:
        """
        Cancel a running worker.

        Args:
            worker_id: ID of the worker to cancel

        Returns:
            True if worker was found and cancelled
        """
        if worker_id in self._active_workers:
            self._active_workers[worker_id].cancel()
            return True
        return False

    def cancel_all(self) -> None:
        """Cancel all active workers."""
        for worker in self._active_workers.values():
            worker.cancel()
        self._active_workers.clear()

    def wait_for_done(self, timeout_ms: int = -1) -> bool:
        """
        Wait for all workers to complete.

        Args:
            timeout_ms: Timeout in milliseconds (-1 for infinite)

        Returns:
            True if all workers completed, False if timeout
        """
        return self.pool.waitForDone(timeout_ms)


_thread_manager: Optional[ThreadManager] = None


def get_thread_manager() -> ThreadManager:
    """Get the global thread manager instance."""
    global _thread_manager
    if _thread_manager is None:
        _thread_manager = ThreadManager()
    return _thread_manager
