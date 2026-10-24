"""
Redact sensitive header diagnostics before logging handlers format them.
The FastAPI application installs this factory once during import.
Provider calls also suppress third-party diagnostic output.
Phase 5 protects the backend Gemini allowance.
All real credentials stay outside source control.
Tests use fake settings and external service doubles.
No module creates settings while being imported.
SQL values are passed separately from SQL text.
The trusted backend owns all database writes.
RLS protects direct access through Supabase clients.
Days follow the Asia/Dubai calendar.
Cached responses do not consume questions.
BYOK requests do not consume server questions.
User keys belong only to the current request.
User keys must never appear in logs.
Authorization headers must never appear in logs.
Missing prices represent an unknown cost.
Cost estimates are not billing statements.
Output token limits also apply to BYOK.
Context token counts are approximate.
Official documents define the shared cache scope.
New ready documents invalidate subject answers.
Not-found responses are never cached.
Errors are never cached.
Sources stay beside the saved answer.
Database migrations are applied manually.
No frontend is added in this phase.
External calls are mocked in offline tests.
Use uv run pytest from the repository root.
Live Gemini checks remain manual.
Live Supabase checks remain manual.
Small helpers keep the request flow readable.
Configuration defaults can be overridden by the user.
"""

import logging
import traceback


def install_header_redaction():
    previous = logging.getLogRecordFactory()
    if getattr(previous, "_notes_redaction", False):
        return

    def make_record(*args, **kwargs):
        record = previous(*args, **kwargs)
        message = record.getMessage().lower()
        if record.exc_info:
            message += "".join(traceback.format_exception(*record.exc_info)).lower()
        if record.stack_info:
            message += record.stack_info.lower()
        # Header dumps can be mappings, byte tuples, or formatted strings.
        # Drop the whole diagnostic instead of guessing where a secret ends.
        if "authorization" in message or "x-user-api-key" in message:
            record.msg = "[redacted sensitive headers]"
            record.args = ()
            record.exc_info = None
            record.exc_text = None
            record.stack_info = None
        return record

    make_record._notes_redaction = True
    logging.setLogRecordFactory(make_record)

