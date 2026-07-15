"""Execution wrapper decorator handling permissions, logging, telemetry, and cancellation."""
from __future__ import annotations

import asyncio
import functools
import time
from typing import Any, List, Optional
from pydantic import ValidationError

from agents.site_intelligence.interfaces import ToolContext
from agents.site_intelligence.models import (
    BaseToolRequest,
    ToolResult,
    PermissionDeniedError,
    ToolTimeoutError,
    ToolValidationError,
    ExternalServiceUnavailableError,
    ToolExecutionError,
)


def translate_exception(exc: Exception) -> Exception:
    """Translate standard exceptions to standardized domain exceptions."""
    if isinstance(
        exc,
        (
            PermissionDeniedError,
            ToolTimeoutError,
            ToolValidationError,
            ExternalServiceUnavailableError,
            ToolExecutionError,
        ),
    ):
        return exc
    if isinstance(exc, ValidationError):
        return ToolValidationError(f"Argument validation failed: {str(exc)}")
    if isinstance(exc, asyncio.TimeoutError):
        return ToolTimeoutError("Task execution timed out.")
    
    # Trace for network/connection/HTTP failures
    msg = str(exc).lower()
    if any(k in msg for k in ["connection", "http", "rate limit", "503", "429", "unreachable", "refused"]):
        return ExternalServiceUnavailableError(f"External service connection unavailable: {str(exc)}")
    
    return ToolExecutionError(f"Internal execution failure: {str(exc)}")


def tool_wrapper(required_permissions: List[str]):
    """Unified decorator wrapping permissions, timing telemetries, cancellation, and exceptions."""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(
            context: ToolContext,
            request: BaseToolRequest,
            cancellation_token: Optional[asyncio.Event] = None,
            *args, **kwargs
        ) -> ToolResult:
            start_time = time.perf_counter()
            tool_name = func.__name__
            success = False
            errors = []
            warnings = []

            try:
                # 1. Permission checks
                for perm in required_permissions:
                    if perm not in context.permissions:
                        raise PermissionDeniedError(f"Unauthorized: missing permission '{perm}'")

                # 2. Check early cancellation
                if cancellation_token and cancellation_token.is_set():
                    raise asyncio.CancelledError("Operation aborted via cancellation token.")

                # 3. Call business logic
                result_payload = await func(context, request, cancellation_token, *args, **kwargs)
                success = True

                # If result_payload is tuple/dict, check for warnings
                if isinstance(result_payload, dict) and "warnings" in result_payload:
                    warnings = result_payload.get("warnings") or []

                return ToolResult(
                    success=True,
                    data=result_payload,
                    warnings=warnings,
                    trace_id=context.trace_id,
                )

            except PermissionDeniedError as e:
                errors.append(str(e))
                raise e
            except asyncio.CancelledError as e:
                errors.append("Cancellation triggered.")
                raise e
            except Exception as exc:
                translated = translate_exception(exc)
                errors.append(str(translated))
                raise translated
            finally:
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                # Ensure telemetry is recorded even when the tool fails
                context.telemetry_service.record_metric(
                    "tool.duration_ms",
                    duration_ms,
                    {"tool": tool_name, "success": str(success)}
                )
                context.telemetry_service.log_structured(
                    "INFO" if success else "ERROR",
                    f"Executed tool {tool_name}",
                    {
                        "trace_id": context.trace_id,
                        "duration_ms": duration_ms,
                        "success": success,
                        "errors": errors,
                    }
                )
        return wrapper
    return decorator
