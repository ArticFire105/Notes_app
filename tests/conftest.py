"""Keep offline API tests isolated from one another.
Each test starts with an empty in-process rate limit.
Production limits are not disabled by this fixture.
The application authenticates users before checking limits.
Limits are keyed by user and request category.
Tests can exercise the real limit functions.
Individual tests may set their own limits.
No real credentials are needed.
No real services are contacted by this fixture.
The fixture does not load configuration.
It does not open a dotenv file.
It does not alter the application database.
It does not change production settings.
FastAPI tests can share one application instance.
That instance otherwise keeps module state between tests.
Clearing the state prevents unrelated tests affecting each other.
The lock protects changes during concurrent requests.
The cleanup runs before and after each test.
That also prevents failed tests leaving state behind.
This fixture belongs to the offline test suite.
Backend tests are collected under the tests directory.
Pytest loads this fixture automatically.
No third-party runtime library is added.
Pytest is already a development dependency.
Test users are synthetic.
User IDs are not credentials.
The limit implementation uses a monotonic clock.
The clock itself is not replaced here.
Tests that need time control can replace it.
Per-user isolation is tested separately.
Category isolation is tested separately.
Limit responses carry a retry delay.
Frontend code displays a fixed safe message.
Run the suite with uv run pytest.
"""

import pytest

from app import auth, main


@pytest.fixture(autouse=True)
def clear_rate_limits(monkeypatch):
    monkeypatch.setattr(main, "recover_interrupted_jobs", lambda: None)
    with auth._rate_lock:
        auth._rate_events.clear()
    yield
    with auth._rate_lock:
        auth._rate_events.clear()
