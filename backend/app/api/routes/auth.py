from fastapi import APIRouter, Request, Response, status

from app.api.deps import CurrentUser, SessionDep
from app.core.config import get_settings
from app.schemas.auth import (
    ChangePasswordIn,
    CompletionTokenOut,
    EmailIn,
    LoginIn,
    MeOut,
    MeUpdateIn,
    ResetCompleteIn,
    SignupCompleteIn,
    VerifyCodeIn,
)
from app.schemas.common import Message
from app.services.auth import flows
from app.services.auth.sessions import revoke_token

router = APIRouter(prefix="/auth", tags=["auth"])

CODE_SENT = Message(message="If that address can receive email, a 6-digit code is on its way.")


def _set_session_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(
        s.session_cookie_name,
        token,
        max_age=s.session_ttl_days * 86400,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(s.session_cookie_name, path="/", secure=s.cookie_secure, httponly=True, samesite="lax")


def _completion(token: str) -> CompletionTokenOut:
    return CompletionTokenOut(
        completion_token=token, expires_in_seconds=get_settings().completion_token_ttl_minutes * 60
    )


# ------------------------------------------------------------------ sign-up


@router.post("/signup/request-code", status_code=status.HTTP_202_ACCEPTED)
async def signup_request_code(body: EmailIn, session: SessionDep) -> Message:
    """Step 1: email a 6-digit code. The response is the same whether or not an account exists."""
    await flows.request_signup_code(session, body.email)
    return CODE_SENT


@router.post("/signup/verify-code")
async def signup_verify_code(body: VerifyCodeIn, session: SessionDep) -> CompletionTokenOut:
    """Step 2: check the code; returns a single-use token for step 3."""
    return _completion(await flows.verify_signup_code(session, body.email, body.code))


@router.post("/signup/complete", status_code=status.HTTP_201_CREATED)
async def signup_complete(body: SignupCompleteIn, request: Request, response: Response, session: SessionDep) -> MeOut:
    """Step 3: choose a password; creates the account (or activates one staff prepared) and logs in."""
    user, token = await flows.complete_signup(
        session,
        completion_token=body.completion_token,
        first_name=body.first_name,
        last_name=body.last_name,
        password=body.password,
        phone=body.phone,
        user_agent=request.headers.get("user-agent"),
    )
    _set_session_cookie(response, token)
    return MeOut.model_validate(user)


# ------------------------------------------------------------------ login / logout


@router.post("/login")
async def login(body: LoginIn, request: Request, response: Response, session: SessionDep) -> MeOut:
    user, token = await flows.login(session, body.email, body.password, request.headers.get("user-agent"))
    _set_session_cookie(response, token)
    return MeOut.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, session: SessionDep) -> None:
    token = request.cookies.get(get_settings().session_cookie_name)
    if token:
        await revoke_token(session, token)
        await session.commit()
    _clear_session_cookie(response)


# ------------------------------------------------------------------ password reset


@router.post("/password-reset/request-code", status_code=status.HTTP_202_ACCEPTED)
async def reset_request_code(body: EmailIn, session: SessionDep) -> Message:
    await flows.request_reset_code(session, body.email)
    return CODE_SENT


@router.post("/password-reset/verify-code")
async def reset_verify_code(body: VerifyCodeIn, session: SessionDep) -> CompletionTokenOut:
    return _completion(await flows.verify_reset_code(session, body.email, body.code))


@router.post("/password-reset/complete")
async def reset_complete(body: ResetCompleteIn, request: Request, response: Response, session: SessionDep) -> MeOut:
    """Sets the new password, signs out every other device, and logs this one in."""
    user, token = await flows.complete_reset(
        session,
        completion_token=body.completion_token,
        new_password=body.new_password,
        user_agent=request.headers.get("user-agent"),
    )
    _set_session_cookie(response, token)
    return MeOut.model_validate(user)


# ------------------------------------------------------------------ me


@router.get("/me")
async def me(user: CurrentUser) -> MeOut:
    return MeOut.model_validate(user)


@router.patch("/me")
async def update_me(body: MeUpdateIn, user: CurrentUser, session: SessionDep) -> MeOut:
    """Only sent fields change. Send "" or null for display_name/phone to clear them."""
    changes = body.model_dump(exclude_unset=True)
    for field in ("first_name", "last_name"):
        if changes.get(field):
            setattr(user, field, changes[field])
    for field in ("display_name", "phone"):
        if field in changes:
            setattr(user, field, changes[field] or None)
    await session.commit()
    return MeOut.model_validate(user)


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(body: ChangePasswordIn, request: Request, user: CurrentUser, session: SessionDep) -> None:
    """Changes the password and signs out every other device."""
    await flows.change_password(
        session,
        user,
        current_password=body.current_password,
        new_password=body.new_password,
        current_session_id=request.state.session_id,
    )
