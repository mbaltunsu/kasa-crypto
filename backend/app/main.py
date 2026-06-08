from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import (
    admin,
    auth,
    deposits,
    faucet,
    me,
    nfts,
    registry,
    transactions,
    transfers,
    wallet,
    withdrawals,
)
from app.core.config import get_settings
from app.core.errors import ErrorResponse, register_error_handlers


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield


def build_api_v1_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    router.include_router(auth.router)
    router.include_router(me.router)
    router.include_router(registry.router)
    router.include_router(wallet.router)
    router.include_router(deposits.router)
    router.include_router(faucet.router)
    router.include_router(withdrawals.router)
    router.include_router(transfers.router)
    router.include_router(transactions.router)
    router.include_router(nfts.router)
    router.include_router(admin.router)
    return router


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="Kasa API",
        version="0.1.0",
        separate_input_output_schemas=False,
        lifespan=lifespan,
        responses={
            400: {"model": ErrorResponse},
            401: {"model": ErrorResponse},
            403: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            429: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
            "default": {"model": ErrorResponse},
        },
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin, "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(application)
    application.include_router(build_api_v1_router())
    return application
