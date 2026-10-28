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


MESSAGES_EN = {
    "validation_error": "The input is not valid. Please correct the highlighted fields.",
    "not_found": "The requested item was not found.",
    "invalid_transition": "This state change is not allowed for the episode.",
    "conflict": "This action does not fit the current state.",
    "provider_unavailable": "The AI service is not available. Check the service type and address in Settings.",
    "llm_invalid_output": "The model did not return valid output (even after several tries). Try again or choose another model.",
    "job_failed": "The job ended with an error. Details are in the production monitor.",
    "ffmpeg_missing": "ffmpeg was not found. START.bat prepares it.",
    "not_ready": "The prerequisites for this action are not ready.",
    "server_error": "Internal error. Details were written to the log file (data\logs).",
    "method_not_allowed": "This request method is not allowed for this address.",
}


def request_language(context) -> str:
    """'en' when the browser asked for English (X-Lang header); anything else means Persian, the default."""
    try:
        return "en" if str(context["request"].headers.get("X-Lang", "")).lower().startswith("en") else "fa"
    except (KeyError, AttributeError, TypeError):
        return "fa"


class DomainError(APIException):
    """Expected business-rule failure with a stable code. `message` is Persian; `message_en` (optional) is shown to English users,
    who otherwise get the generic English text of the code."""

    status_code = status.HTTP_409_CONFLICT

    def __init__(self, code: str, message: str | None = None, *, http_status: int | None = None, details=None, message_en: str | None = None):
        self.code = code
        self.details = details
        self.message_en = message_en
        if http_status:
            self.status_code = http_status
        super().__init__(detail=message or MESSAGES_FA.get(code, code))


def _error(code: str, message: str, http_status: int, details=None) -> Response:
    body = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return Response(body, status=http_status)


def _text(code: str, fa: str, lang: str, en: str | None = None) -> str:
    return fa if lang != "en" else (en or MESSAGES_EN.get(code) or fa)


def api_exception_handler(exc, context):
    resp = exception_handler(exc, context)
    lang = request_language(context)
    if isinstance(exc, DomainError):
        return _error(exc.code, _text(exc.code, str(exc.detail), lang, exc.message_en), exc.status_code, exc.details)
    if resp is None:
        import logging

        logging.getLogger("instai").exception("unhandled API error")
        return _error("server_error", _text("server_error", MESSAGES_FA["server_error"], lang), 500)
    if isinstance(exc, ValidationError):
        return _error("validation_error", _text("validation_error", MESSAGES_FA["validation_error"], lang), 400, resp.data)
    if resp.status_code == 404:
        return _error("not_found", _text("not_found", MESSAGES_FA["not_found"], lang), 404)
    if resp.status_code == 405:
        return _error("method_not_allowed", _text("method_not_allowed", MESSAGES_FA["method_not_allowed"], lang), 405)
    detail = resp.data.get("detail") if isinstance(resp.data, dict) else None
    return _error("error", str(detail or ("Error" if lang == "en" else "خطا")), resp.status_code)
