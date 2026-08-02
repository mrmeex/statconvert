"""Stable API errors for the initial browser UI shell."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from statconvert.exceptions import StatConvertError


MISSING_STATIC_ASSETS_MESSAGE = (
    "The StatConvert UI frontend assets are missing. "
    "Build the frontend for development or reinstall the official wheel with UI assets."
)


def missing_static_assets_response() -> JSONResponse:
    """Return a clear packaging/development error instead of a blank page."""

    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "ui_static_assets_missing",
                "message": MISSING_STATIC_ASSETS_MESSAGE,
            }
        },
    )


def install_error_handlers(application: FastAPI) -> None:
    """Install stable JSON errors without exposing local tracebacks."""

    @application.exception_handler(RequestValidationError)
    async def request_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        del request
        return _error_response(
            status_code=422,
            code="request_validation_error",
            message="The request contains invalid or missing fields.",
            details={"issues": exc.errors()},
        )

    @application.exception_handler(StatConvertError)
    async def statconvert_error(
        request: Request,
        exc: StatConvertError,
    ) -> JSONResponse:
        del request
        return _error_response(
            status_code=400,
            code=_error_code(exc),
            message=exc.message,
            suggestion=exc.suggestion,
        )

    @application.exception_handler(ValueError)
    async def value_error(request: Request, exc: ValueError) -> JSONResponse:
        del request
        return _error_response(
            status_code=400,
            code=_error_code(exc),
            message=str(exc),
        )

    @application.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        del request, exc
        return _error_response(
            status_code=500,
            code="internal_error",
            message="The local StatConvert UI could not complete this request.",
        )


def job_not_found_response(job_id: str) -> JSONResponse:
    return _error_response(
        status_code=404,
        code="job_not_found",
        message=f"Job was not found: {job_id}",
    )


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    suggestion: str | None = None,
    details: dict[str, object] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "suggestion": suggestion,
                "details": details or {},
            }
        },
    )


def _error_code(exc: Exception) -> str:
    name = exc.__class__.__name__
    return "".join(
        f"_{character.lower()}" if character.isupper() else character
        for character in name
    ).lstrip("_")
