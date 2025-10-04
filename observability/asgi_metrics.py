from prometheus_client import make_asgi_app
from starlette.responses import Response
from starlette.requests import Request
import asyncio
import logging

from .metrics import collect_once

logger = logging.getLogger(__name__)

# We will create a small wrapper ASGI app that refreshes our custom gauges
# before delegating to the standard prometheus ASGI app

_metrics_app = make_asgi_app()

async def app(scope, receive, send):
    # Only run collection for HTTP requests
    if scope['type'] == 'http':
        try:
            await collect_once()
        except Exception as e:
            logger.error(f"Error during observability collect_once: {e}")
    await _metrics_app(scope, receive, send)
