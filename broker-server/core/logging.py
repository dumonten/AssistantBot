import json
import sys
import time
from typing import Callable

from fastapi import Request
from fastapi import Response as FastAPIResponse
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

from core.config import settings


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for detailed logging of HTTP requests and responses.

    Logs request method, URL, client address, request body, response body,
    and processing time for debugging and monitoring purposes.
    """

    TRUNCATE_CHAR_LIMIT: int = 1000

    async def dispatch(self, request: Request, call_next: Callable) -> FastAPIResponse:
        """
        Process the request and log details before and after processing.

        Args:
            request: Incoming request object
            call_next: Next middleware/function in the chain

        Returns:
            Processed response object
        """
        start_time = time.time()
        # Get client info
        client_host = request.client.host if request.client else "unknown"
        client_port = request.client.port if request.client else "unknown"
        remote_addr = f"{client_host}:{client_port}"
        # Log request details
        request_body_log = None
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.body()
                request._body = body
                if body:
                    content_type = request.headers.get("content-type", "").lower()
                    if "application/json" in content_type:
                        try:
                            request_body = json.loads(body)
                            request_body_log = json.dumps(
                                request_body, indent=None, ensure_ascii=False
                            )
                        except json.JSONDecodeError:
                            request_body_log = body.decode("utf-8", errors="replace")
                    elif content_type.startswith("text/"):
                        request_body_log = body.decode("utf-8", errors="replace")
                    else:
                        request_body_log = f"Type: {content_type} - not logged"
            except Exception as e:
                logger.error(f"Error reading request body: {e}")
                request_body_log = "[Error reading body]"
        if request_body_log and len(request_body_log) > self.TRUNCATE_CHAR_LIMIT:
            request_body_log = (
                request_body_log[: self.TRUNCATE_CHAR_LIMIT] + "... (truncated)"
            )
        logger.info(
            f"{request.method} {request.url.path} | {remote_addr} | Request Body: {request_body_log}"
        )
        # Process the request
        response = await call_next(request)
        # Capture and log response body (buffering it for logging)
        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        # Rebuild the body iterator to avoid consumption
        async def new_body_iterator():
            yield body

        response.body_iterator = new_body_iterator()
        response_body_log = None
        if body:
            content_type = response.headers.get("content-type", "").lower()
            if "application/json" in content_type:
                try:
                    response_body = json.loads(body.decode("utf-8", errors="replace"))
                    response_body_log = json.dumps(
                        response_body, indent=None, ensure_ascii=False
                    )
                except Exception as e:
                    logger.error(f"Error parsing JSON response body: {e}")
                    response_body_log = "[Invalid JSON]"
            elif content_type.startswith("text/"):
                response_body_log = body.decode("utf-8", errors="replace")
            else:
                response_body_log = f"Type: {content_type} - not logged"
        if response_body_log and len(response_body_log) > self.TRUNCATE_CHAR_LIMIT:
            response_body_log = (
                response_body_log[: self.TRUNCATE_CHAR_LIMIT] + "... (truncated)"
            )
        process_time = time.time() - start_time
        log_msg = f"{response.status_code} | {request.method} {request.url.path} | {remote_addr} | Time: {process_time:.4f}s | Response Body: {response_body_log}"
        if response.status_code == 200:
            logger.info(log_msg)
        else:
            logger.error(log_msg)
        return response


def setup_logging():
    """
    Configure the application logging with console and file handlers.

    Sets up logging with the configured log level, adds console handler with
    colorization, and file handler with rotation and retention policies.
    """
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.LOG_LEVEL,
        colorize=True,
    )

    logger.add(
        settings.log_file_path,
        rotation=settings.LOG_ROTATION,
        retention=settings.LOG_RETENTION,
        level=settings.LOG_LEVEL,
        enqueue=True,
    )
