"""Embedded HTTP control server for external UI control.

Runs a lightweight HTTP server in a QThread, allowing external tools
(like an MCP server) to control the investment tool UI.

Listens on localhost:18765 by default.
"""

import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, Dict, Any

from PySide6.QtCore import QThread, Signal, QMutex, QWaitCondition
from loguru import logger


class _RequestState:
    """Shared state for synchronizing HTTP request/response with Qt main thread."""

    def __init__(self):
        self.mutex = QMutex()
        self.condition = QWaitCondition()
        self.result: Optional[Dict[str, Any]] = None
        self.pending_action: Optional[Dict[str, Any]] = None


class ControlRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the control API."""

    # Class-level reference to the control server (set by ControlServer)
    control_server: Optional["ControlServer"] = None

    def log_message(self, format, *args):
        """Redirect HTTP server logs to loguru."""
        logger.debug(f"ControlAPI: {format % args}")

    def _send_json(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _read_body(self) -> dict:
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        body = self.rfile.read(content_length)
        return json.loads(body.decode())

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self._send_json({"status": "ok"})
        elif self.path == "/state":
            self._handle_get_state()
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        try:
            body = self._read_body()
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({"error": f"Invalid JSON: {e}"}, 400)
            return

        if self.path == "/select-stock":
            self._handle_select_stock(body)
        elif self.path == "/set-period":
            self._handle_set_period(body)
        else:
            self._send_json({"error": "Not found"}, 404)

    def _handle_get_state(self):
        server = self.control_server
        if not server:
            self._send_json({"error": "Server not initialized"}, 500)
            return

        # Request state from main thread via signal
        server.state_requested.emit()

        # Wait for the main thread to provide the result
        state = server._wait_for_result(timeout_ms=5000)
        if state is not None:
            self._send_json(state)
        else:
            self._send_json({"error": "Timeout waiting for UI state"}, 504)

    def _handle_select_stock(self, body: dict):
        server = self.control_server
        if not server:
            self._send_json({"error": "Server not initialized"}, 500)
            return

        ticker = body.get("ticker")
        exchange = body.get("exchange", "US")

        if not ticker:
            self._send_json({"error": "Missing 'ticker' field"}, 400)
            return

        # Emit signal to select stock on main thread
        server.select_stock_requested.emit(ticker, exchange)

        # Wait for completion
        result = server._wait_for_result(timeout_ms=15000)
        if result is not None:
            self._send_json(result)
        else:
            self._send_json({"status": "ok", "note": "Action dispatched (timeout waiting for confirmation)"})

    def _handle_set_period(self, body: dict):
        server = self.control_server
        if not server:
            self._send_json({"error": "Server not initialized"}, 500)
            return

        period = body.get("period")
        valid_periods = ("1D", "1W", "1M", "3M", "6M", "1Y", "5Y")
        if not period or period not in valid_periods:
            self._send_json(
                {"error": f"Invalid period. Must be one of: {', '.join(valid_periods)}"},
                400,
            )
            return

        # Emit signal to change period on main thread
        server.set_period_requested.emit(period)

        # Wait for completion
        result = server._wait_for_result(timeout_ms=15000)
        if result is not None:
            self._send_json(result)
        else:
            self._send_json({"status": "ok", "note": "Action dispatched (timeout waiting for confirmation)"})


class ControlServer(QThread):
    """QThread-based HTTP control server.

    Signals are emitted to execute actions on the Qt main thread.
    A QWaitCondition is used to block the HTTP response until the
    main thread completes the action.
    """

    # Signals emitted to main thread
    state_requested = Signal()
    select_stock_requested = Signal(str, str)  # ticker, exchange
    set_period_requested = Signal(str)  # period

    def __init__(self, port: int = 18765, parent=None):
        super().__init__(parent)
        self._port = port
        self._server: Optional[HTTPServer] = None
        self._request_state = _RequestState()
        self.daemon = True

        # Set class-level reference so handler can access this server
        ControlRequestHandler.control_server = self

    def run(self):
        """Run the HTTP server in this thread."""
        try:
            self._server = HTTPServer(("127.0.0.1", self._port), ControlRequestHandler)
            logger.info(f"Control API server started on http://127.0.0.1:{self._port}")
            self._server.serve_forever()
        except OSError as e:
            logger.error(f"Control API server failed to start: {e}")
        except Exception as e:
            logger.error(f"Control API server error: {e}")

    def stop(self):
        """Stop the HTTP server."""
        if self._server:
            self._server.shutdown()
            logger.info("Control API server stopped")

    def provide_result(self, result: Dict[str, Any]):
        """Called from main thread to provide result back to HTTP handler."""
        self._request_state.mutex.lock()
        self._request_state.result = result
        self._request_state.condition.wakeAll()
        self._request_state.mutex.unlock()

    def _wait_for_result(self, timeout_ms: int = 5000) -> Optional[Dict[str, Any]]:
        """Wait for the main thread to provide a result. Called from HTTP thread."""
        self._request_state.mutex.lock()
        self._request_state.result = None
        # Wait for main thread to call provide_result
        got_result = self._request_state.condition.wait(
            self._request_state.mutex, timeout_ms
        )
        result = self._request_state.result
        self._request_state.mutex.unlock()
        return result if got_result else None
