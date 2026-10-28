"""
Track server-key request reservations, tokens, and estimated costs.
The ask router reserves before generation and records usage afterward.
A transaction lock makes the global check and reservation indivisible.
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

from decimal import Decimal

from app.config import Settings
from app.db import get_conn

TODAY = "(now() at time zone 'Asia/Dubai')::date"
# A fixed transaction lock coordinates all backend workers using this database.
QUOTA_LOCK = 5004001


def dubai_day():
    with get_conn() as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"select {TODAY}")
            return cursor.fetchone()[0]


def estimate_cost(input_tokens, output_tokens, settings=None):
    settings = settings or Settings()
    if not settings.price_input_per_1m_usd or not settings.price_output_per_1m_usd:
        return None
    return (
        Decimal(input_tokens) * settings.price_input_per_1m_usd
        + Decimal(output_tokens) * settings.price_output_per_1m_usd
    ) / Decimal(1_000_000)


def totals(cursor, day=None):
    cursor.execute(
        f"""select coalesce(sum(requests), 0), coalesce(sum(input_tokens), 0),
                   coalesce(sum(output_tokens), 0), coalesce(sum(est_cost_usd), 0)
            from usage_daily where day = coalesce(%s::date, {TODAY})""",
        (day,),
    )
    return cursor.fetchone()


def global_ok(cursor=None, settings=None, day=None):
    settings = settings or Settings()
    if cursor is None:
        with get_conn() as connection:
            with connection.cursor() as local_cursor:
                return global_ok(local_cursor, settings, day)
    requests, _, _, cost = totals(cursor, day)
    if requests >= settings.global_daily_cap:
        return False
    budget = settings.global_daily_budget_usd
    # A configured budget cannot protect credits without known prices.
    if budget is not None:
        # Completed-call estimates lag in-flight requests; the request cap is
        # strict, while this budget can overshoot by calls already reserved.
        return estimate_cost(0, 0, settings) is not None and cost < budget
    return True


def try_consume(user_id, day=None):
    settings = Settings()
    with get_conn() as connection:
        with connection.cursor() as cursor:
            # Separate SELECT/UPDATE calls race across tabs. The global lock also
            # prevents different users reserving the final global slot together.
            cursor.execute("select pg_advisory_xact_lock(%s)", (QUOTA_LOCK,))
            if not global_ok(cursor, settings, day):
                return False
            cursor.execute(
                f"""insert into usage_daily (user_id, day, requests)
                    values (%s, coalesce(%s::date, {TODAY}), 1)
                    on conflict (user_id, day) do update
                    set requests = usage_daily.requests + 1
                    where usage_daily.requests < %s
                    returning requests""",
                (user_id, day, settings.questions_per_day),
            )
            return cursor.fetchone() is not None


def release_empty(user_id, day):
    # Empty retrieval makes no Gemini call, so give that reservation back.
    with get_conn() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """update usage_daily set requests = greatest(requests - 1, 0)
                   where user_id = %s and day = %s""", (user_id, day),
            )


def record_usage(user_id, input_tokens, output_tokens, day=None):
    cost = estimate_cost(input_tokens, output_tokens)
    with get_conn() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""update usage_daily
                    set input_tokens = input_tokens + %s,
                        output_tokens = output_tokens + %s,
                        est_cost_usd = est_cost_usd + %s
                    where user_id = %s and day = coalesce(%s::date, {TODAY})""",
                (input_tokens, output_tokens, cost or Decimal(0), user_id, day),
            )


def user_usage(user_id):
    settings = Settings()
    with get_conn() as connection:
        with connection.cursor() as cursor:
            # SQL supplies both today's count and the next Dubai midnight.
            cursor.execute(
                f"""select coalesce((select requests from usage_daily
                        where user_id = %s and day = {TODAY}), 0),
                       (({TODAY} + 1)::timestamp at time zone 'Asia/Dubai')""",
                (user_id,),
            )
            used, resets_at = cursor.fetchone()
    return {"used": used, "limit": settings.questions_per_day, "resets_at": resets_at}


def remaining(user_id):
    usage = user_usage(user_id)
    return max(usage["limit"] - usage["used"], 0)


def admin_usage():
    settings = Settings()
    with get_conn() as connection:
        with connection.cursor() as cursor:
            requests, input_tokens, output_tokens, cost = totals(cursor)
    return {
        "total_requests": requests, "total_input_tokens": input_tokens,
        "total_output_tokens": output_tokens,
        "est_cost_usd": cost if estimate_cost(0, 0, settings) is not None else "unknown",
        "global_cap": settings.global_daily_cap,
    }

