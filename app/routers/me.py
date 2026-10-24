"""
Return the signed-in user's email and role.
This route belongs to Phase 4.
It supports local authentication checks.
The later frontend can use the same response.

FastAPI resolves authentication before this handler.
Supabase verifies the request's bearer token.
The college domain check runs on the backend.
The profile supplies the current role.

Email comes from the verified identity.
Role comes from the application database.
Request bodies cannot select another user.
Request bodies cannot select another role.

Only email and role leave this handler.
The internal profile ID stays on the backend.
Access tokens never appear in responses.
Configuration never appears in responses.

Missing authentication produces a 401 response.
An invalid token produces a 401 response.
A disallowed email domain produces a 403 response.
A missing profile produces a 401 response.

Students can inspect their own identity.
Representatives can inspect their own identity.
Administrators can inspect their own identity.
This route does not modify profiles.

Roles are changed manually through trusted SQL.
No client role-update endpoint is provided.
Tests replace the external authentication services.
The response is deliberately small and readable.
No additional database query is needed in this handler.
"""

from fastapi import APIRouter, Depends

from app.auth import get_current_user, require_role
from app import quota
from app.llm import test_user_key, user_api_key

router = APIRouter()


@router.get("/me")
def me(user=Depends(get_current_user)):
    return {"email": user["email"], "role": user["role"]}


@router.get("/me/usage")
def my_usage(user=Depends(get_current_user)):
    return quota.user_usage(user["id"])


@router.get("/admin/usage/today")
def today_usage(user=Depends(require_role("admin"))):
    return quota.admin_usage()


@router.post("/me/test-key")
def check_key(user=Depends(get_current_user), api_key=Depends(user_api_key)):
    return test_user_key(api_key)
