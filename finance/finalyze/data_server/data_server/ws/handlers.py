"""WebSocket message handlers."""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from data_server.ws.manager import manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    client_id = str(uuid.uuid4())
    await manager.connect(websocket, client_id)

    try:
        # Send initial connection confirmation
        await manager.send_personal(
            client_id,
            {
                "type": "connected",
                "client_id": client_id,
                "message": "Connected to data server",
            },
        )

        while True:
            # Receive and process messages from client
            data = await websocket.receive_json()
            await handle_message(client_id, data)

    except WebSocketDisconnect:
        logger.info(f"Client {client_id} disconnected")
    except Exception as e:
        logger.error(f"WebSocket error for {client_id}: {e}")
    finally:
        await manager.disconnect(client_id)


async def handle_message(client_id: str, data: dict):
    """Handle incoming WebSocket messages."""
    msg_type = data.get("type")

    if msg_type == "subscribe":
        tickers = data.get("tickers", [])
        if tickers:
            await manager.subscribe(client_id, tickers)
            await manager.send_personal(
                client_id,
                {
                    "type": "subscribed",
                    "tickers": tickers,
                },
            )
            logger.info(f"Client {client_id} subscribed to: {tickers}")

    elif msg_type == "unsubscribe":
        tickers = data.get("tickers", [])
        if tickers:
            await manager.unsubscribe(client_id, tickers)
            await manager.send_personal(
                client_id,
                {
                    "type": "unsubscribed",
                    "tickers": tickers,
                },
            )
            logger.info(f"Client {client_id} unsubscribed from: {tickers}")

    elif msg_type == "ping":
        await manager.send_personal(client_id, {"type": "pong"})

    elif msg_type == "get_subscriptions":
        subs = await manager.get_subscriptions(client_id)
        await manager.send_personal(
            client_id,
            {
                "type": "subscriptions",
                "tickers": list(subs),
            },
        )

    else:
        logger.warning(f"Unknown message type from {client_id}: {msg_type}")
        await manager.send_personal(
            client_id,
            {
                "type": "error",
                "message": f"Unknown message type: {msg_type}",
            },
        )
