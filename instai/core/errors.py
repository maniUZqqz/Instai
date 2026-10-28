"""One error shape for the whole API: {"error": {"code", "message", "details"}} with Persian messages."""
from __future__ import annotations

from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler

MESSAGES_FA = {
    "validation_error": "ورودی نامعتبر است. فیلدهای مشخص‌شده را اصلاح کنید.",
    "not_found": "مورد خواسته‌شده پیدا نشد.",
    "invalid_transition": "این تغییر وضعیت برای قسمت مجاز نیست.",
    "conflict": "این کار با وضعیت فعلی سازگار نیست.",
    "provider_unavailable": "سرویس هوش مصنوعی در دسترس نیست. در تنظیمات، نوع و نشانی سرویس را بررسی کنید.",
    "llm_invalid_output": "مدل خروجی معتبر نداد (حتی پس از چند بار تلاش). دوباره امتحان کنید یا مدل دیگری انتخاب کنید.",
    "job_failed": "کار با خطا تمام شد. جزئیات در «پایش تولید» است.",
    "ffmpeg_missing": "ابزار ffmpeg پیدا نشد. START.bat آن را آماده می‌کند.",
    "not_ready": "پیش‌نیازهای این کار آماده نیست.",
    "server_error": "خطای داخلی برنامه. جزئیات در پرونده‌ی گزارش (data\\logs) ثبت شد.",
    "method_not_allowed": "این روش درخواست برای این آدرس مجاز نیست.",
}


class DomainError(APIException):
    """Expected business-rule failure with a stable code."""

    status_code = status.HTTP_409_CONFLICT

    def __init__(self, code: str, message: str | None = None, *, http_status: int | None = None, details=None):
        self.code = code
        self.details = details
        if http_status:
            self.status_code = http_status
        super().__init__(detail=message or MESSAGES_FA.get(code, code))


def _error(code: str, message: str, http_status: int, details=None) -> Response:
    body = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return Response(body, status=http_status)


def api_exception_handler(exc, context):
    resp = exception_handler(exc, context)
    if isinstance(exc, DomainError):
        return _error(exc.code, str(exc.detail), exc.status_code, exc.details)
    if resp is None:
        import logging

        logging.getLogger("instai").exception("unhandled API error")
        return _error("server_error", MESSAGES_FA["server_error"], 500)
    if isinstance(exc, ValidationError):
        return _error("validation_error", MESSAGES_FA["validation_error"], 400, resp.data)
    if resp.status_code == 404:
        return _error("not_found", MESSAGES_FA["not_found"], 404)
    if resp.status_code == 405:
        return _error("method_not_allowed", MESSAGES_FA["method_not_allowed"], 405)
    detail = resp.data.get("detail") if isinstance(resp.data, dict) else None
    return _error("error", str(detail or "خطا"), resp.status_code)
