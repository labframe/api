"""Server-Sent Events (SSE) connection manager for broadcasting database changes."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import Request
from fastapi.responses import StreamingResponse


class SSEManager:
    """Manages SSE connections and broadcasts notifications."""

    def __init__(self) -> None:
        # Map project_name -> list of queues
        self._connections: dict[str | None, list[asyncio.Queue[str]]] = {}

    async def subscribe(self, project_name: str | None) -> asyncio.Queue[str]:
        """Subscribe to change notifications for a project."""
        queue: asyncio.Queue[str] = asyncio.Queue()
        if project_name not in self._connections:
            self._connections[project_name] = []
        self._connections[project_name].append(queue)
        return queue

    async def unsubscribe(self, project_name: str | None, queue: asyncio.Queue[str]) -> None:
        """Unsubscribe from change notifications."""
        if project_name in self._connections:
            try:
                self._connections[project_name].remove(queue)
                if not self._connections[project_name]:
                    del self._connections[project_name]
            except ValueError:
                pass  # Queue not in list (already removed)

    async def broadcast(self, project_name: str | None, notification: dict[str, Any]) -> None:
        """Broadcast a notification to all subscribers of a project."""
        queues = self._connections.get(project_name, [])
        message = f"data: {json.dumps(notification)}\n\n"

        # Remove dead queues
        active_queues = []
        for queue in queues:
            try:
                queue.put_nowait(message)
                active_queues.append(queue)
            except asyncio.QueueFull:
                # Queue is full, skip it
                pass
            except Exception:
                # Queue is dead, skip it
                pass

        # Update connections list
        if active_queues:
            self._connections[project_name] = active_queues
        elif project_name in self._connections:
            del self._connections[project_name]

    async def stream_events(
        self,
        request: Request,
        project_name: str | None,
    ) -> StreamingResponse:
        """Create an SSE stream for a client."""
        queue = await self.subscribe(project_name)

        async def event_generator() -> Any:
            try:
                # Send initial connection message
                yield "data: {\"type\":\"connected\"}\n\n"

                while True:
                    # Check if client disconnected
                    if await request.is_disconnected():
                        break

                    try:
                        # Wait for message with timeout
                        message = await asyncio.wait_for(queue.get(), timeout=1.0)
                        yield message
                    except asyncio.TimeoutError:
                        # Send heartbeat to keep connection alive
                        yield ": heartbeat\n\n"
                        continue

            finally:
                # Clean up on disconnect
                await self.unsubscribe(project_name, queue)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            },
        )


# Global SSE manager instance
_sse_manager = SSEManager()


def get_sse_manager() -> SSEManager:
    """Get the global SSE manager instance."""
    return _sse_manager

