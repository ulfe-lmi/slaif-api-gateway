"""Streaming responses which preserve HTTP errors before the first event."""

import anyio
from starlette.responses import StreamingResponse
from starlette.types import Send


class DeferredStartStreamingResponse(StreamingResponse):
    """Pull one event before committing headers, without buffering the stream.

    Starlette still owns disconnect handling and background-task execution.
    The producer owns accounting and converts early failures to HTTP errors.
    """

    async def stream_response(self, send: Send) -> None:
        iterator = aiter(self.body_iterator)
        try:
            try:
                first = await anext(iterator)
            except StopAsyncIteration:
                first = None
            await send(
                {
                    "type": "http.response.start",
                    "status": self.status_code,
                    "headers": self.raw_headers,
                }
            )
            if first is not None:
                if not isinstance(first, (bytes, memoryview)):
                    first = first.encode(self.charset)
                await send({"type": "http.response.body", "body": first, "more_body": True})
            async for chunk in iterator:
                if not isinstance(chunk, (bytes, memoryview)):
                    chunk = chunk.encode(self.charset)
                await send({"type": "http.response.body", "body": chunk, "more_body": True})
            await send({"type": "http.response.body", "body": b"", "more_body": False})
        finally:
            # A disconnect may happen while the iterator is suspended at yield.
            # Closing it runs the producer's existing shielded cleanup now.
            close = getattr(iterator, "aclose", None)
            if close is not None:
                with anyio.CancelScope(shield=True):
                    await close()
