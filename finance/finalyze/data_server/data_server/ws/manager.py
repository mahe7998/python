"""WebSocket connection manager."""

import asyncio
import json
import logging
from typing import Any, Optional
from dataclasses import dataclass, field

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


@dataclass
class Connection:
    """Represents a WebSocket connection."""

    websocket: WebSocket
    subscribed_tickers: set[str] = field(default_factory=set)


class ConnectionManager:
    """Manages WebSocket connections and message broadcasting."""

    def __init__(self):
        self.connections: dict[str, Connection] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, client_id: str):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self.connections[client_id] = Connection(websocket=websocket)
        logger.info(f"WebSocket connected: {client_id}")

    async def disconnect(self, client_id: str):
        """Remove a WebSocket connection."""
        async with self._lock:
            if client_id in self.connections:
                del self.connections[client_id]
        logger.info(f"WebSocket disconnected: {client_id}")

    async def disconnect_all(self):
        """Disconnect all WebSocket connections."""
        async with self._lock:
            for client_id, conn in list(self.connections.items()):
                try:
                    await conn.websocket.close()
                except Exception:
                    pass
            self.connections.clear()
        logger.info("All WebSocket connections closed")

    async def subscribe(self, client_id: str, tickers: list[str]):
        """Subscribe a client to tickers."""
        async with self._lock:
            if client_id in self.connections:
                self.connections[client_id].subscribed_tickers.update(tickers)
                logger.debug(f"Client {client_id} subscribed to: {tickers}")

    async def unsubscribe(self, client_id: str, tickers: list[str]):
        """Unsubscribe a client from tickers."""
        async with self._lock:
            if client_id in self.connections:
                self.connections[client_id].subscribed_tickers.difference_update(tickers)
                logger.debug(f"Client {client_id} unsubscribed from: {tickers}")

    async def get_subscriptions(self, client_id: str) -> set[str]:
        """Get subscribed tickers for a client."""
        async with self._lock:
            if client_id in self.connections:
                return self.connections[client_id].subscribed_tickers.copy()
            return set()

    async def send_personal(self, client_id: str, message: dict):
        """Send a message to a specific client."""
        async with self._lock:
            if client_id in self.connections:
                try:
                    await self.connections[client_id].websocket.send_json(message)
                except Exception as e:
                    logger.error(f"Error sending to {client_id}: {e}")

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected clients."""
        async with self._lock:
            for client_id, conn in list(self.connections.items()):
                try:
                    await conn.websocket.send_json(message)
                except Exception as e:
                    logger.error(f"Error broadcasting to {client_id}: {e}")

    async def broadcast_to_ticker(self, ticker: str, message: dict):
        """Broadcast a message to clients subscribed to a ticker."""
        async with self._lock:
            for client_id, conn in list(self.connections.items()):
                if ticker in conn.subscribed_tickers:
                    try:
                        await conn.websocket.send_json(message)
                    except Exception as e:
                        logger.error(f"Error sending to {client_id}: {e}")

    async def broadcast_price_update(self, ticker: str, data: dict):
        """Broadcast a price update to subscribed clients."""
        message = {
            "type": "price_update",
            "ticker": ticker,
            "data": data,
        }
        await self.broadcast_to_ticker(ticker, message)

    async def broadcast_news_update(self, ticker: str, data: dict):
        """Broadcast a news update to subscribed clients."""
        message = {
            "type": "news_update",
            "ticker": ticker,
            "data": data,
        }
        await self.broadcast_to_ticker(ticker, message)

    async def broadcast_tracking_status(self, data: dict):
        """Broadcast tracking status to all clients."""
        message = {
            "type": "tracking_status",
            "data": data,
        }
        await self.broadcast(message)

    @property
    def connection_count(self) -> int:
        """Get the number of active connections."""
        return len(self.connections)

    def get_all_subscribed_tickers(self) -> set[str]:
        """Get all tickers that have at least one subscriber."""
        tickers = set()
        for conn in self.connections.values():
            tickers.update(conn.subscribed_tickers)
        return tickers


# Global manager instance
manager = ConnectionManager()
