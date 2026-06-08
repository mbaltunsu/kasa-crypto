from collections.abc import Sequence
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import ErrorCode


class ErrorResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    code: ErrorCode
    message: str
    details: list[str] = Field(default_factory=list)
    request_id: str | None = None


def _request_id(request: Request) -> str | None:
    state_request_id = getattr(request.state, "request_id", None)
    if isinstance(state_request_id, str):
        return state_request_id
    header_request_id = request.headers.get("x-request-id")
    return header_request_id or None


def _response(
    request: Request,
    *,
    status_code: int,
    code: ErrorCode,
    message: str,
    details: Sequence[str] = (),
) -> JSONResponse:
    payload = ErrorResponse(
        code=code,
        message=message,
        details=list(details),
        request_id=_request_id(request),
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


def _http_error_code(status_code: int) -> ErrorCode:
    return {
        400: ErrorCode.VALIDATION_ERROR,
        401: ErrorCode.UNAUTHORIZED,
        403: ErrorCode.UNAUTHORIZED,
        404: ErrorCode.NOT_FOUND,
        409: ErrorCode.VALIDATION_ERROR,
        422: ErrorCode.VALIDATION_ERROR,
        429: ErrorCode.RATE_LIMITED,
    }.get(status_code, ErrorCode.INTERNAL_ERROR)


async def request_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    details = [str(error.get("msg", "validation error")) for error in exc.errors()]
    return _response(
        request,
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        code=ErrorCode.VALIDATION_ERROR,
        message="Request validation failed",
        details=details,
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail: Any = exc.detail
    code = _http_error_code(exc.status_code)
    try:
        message = HTTPStatus(exc.status_code).phrase
    except ValueError:
        message = "HTTP error"
    details: list[str] = []

    if isinstance(detail, dict):
        raw_code = detail.get("code")
        if isinstance(raw_code, str):
            try:
                code = ErrorCode(raw_code)
            except ValueError:
                code = _http_error_code(exc.status_code)
        raw_message = detail.get("message")
        if isinstance(raw_message, str):
            message = raw_message
        raw_details = detail.get("details")
        if isinstance(raw_details, list):
            details = [item for item in raw_details if isinstance(item, str)]
    elif isinstance(detail, str):
        message = detail

    return _response(
        request,
        status_code=exc.status_code,
        code=code,
        message=message,
        details=details,
    )


async def unhandled_exception_handler(request: Request, _exc: Exception) -> JSONResponse:
    return _response(
        request,
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        code=ErrorCode.INTERNAL_ERROR,
        message="Internal server error",
        details=[],
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
