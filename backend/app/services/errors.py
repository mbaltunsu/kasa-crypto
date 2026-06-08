from http import HTTPStatus
from typing import NoReturn

from fastapi import HTTPException

from app.core.enums import ErrorCode


def raise_api_error(status_code: int, code: ErrorCode, message: str) -> NoReturn:
    raise HTTPException(
        status_code=status_code,
        detail={"code": code.value, "message": message, "details": []},
    )


def raise_not_found(message: str = "Not found") -> NoReturn:
    raise_api_error(HTTPStatus.NOT_FOUND, ErrorCode.NOT_FOUND, message)
