"""Plain-text email templates. Each renders (subject, body) from the params stored in the outbox."""

from collections.abc import Callable
from typing import Any

from app.core.config import get_settings

SIGNATURE = "\n\n— Al Hidayah Academy Sunday School"

# Params removed from the outbox row once the email is sent (never keep codes around).
SECRET_PARAMS = {"code"}


def _signup_code(p: dict[str, Any]) -> tuple[str, str]:
    return (
        f"Your Al Hidayah Academy verification code: {p['code']}",
        f"Your verification code is {p['code']}.\n\n"
        f"Enter it on the sign-up page to continue. It expires in {p['ttl_minutes']} minutes.\n"
        "If you didn't ask for this, you can ignore this email." + SIGNATURE,
    )


def _reset_code(p: dict[str, Any]) -> tuple[str, str]:
    return (
        f"Your Al Hidayah Academy password reset code: {p['code']}",
        f"Your password reset code is {p['code']}. It expires in {p['ttl_minutes']} minutes.\n\n"
        "If you didn't ask to reset your password, you can ignore this email — your password is unchanged." + SIGNATURE,
    )


def _account_exists(p: dict[str, Any]) -> tuple[str, str]:
    return (
        "You already have an Al Hidayah Academy account",
        "Someone (hopefully you) tried to sign up with this email address, but it already has an account.\n\n"
        f"You can log in at {get_settings().app_base_url}, or use “Forgot password” if you can't remember it."
        + SIGNATURE,
    )


def _account_invite(p: dict[str, Any]) -> tuple[str, str]:
    return (
        "You've been invited to the Al Hidayah Academy sign-up system",
        f"Assalamu alaikum {p['first_name']},\n\n"
        f"An account has been prepared for you with the role: {p['role']}.\n"
        f"To activate it, go to {get_settings().app_base_url} and sign up with this email address "
        "— we'll send you a verification code, then you'll choose a password." + SIGNATURE,
    )


def _enrollment_approved(p: dict[str, Any]) -> tuple[str, str]:
    return (
        f"Approved: {p['student_name']} — {p['class_name']}",
        f"Good news! {p['student_name']}'s enrollment in {p['class_name']} ({p['period_label']}) has been approved."
        + SIGNATURE,
    )


def _enrollment_rejected(p: dict[str, Any]) -> tuple[str, str]:
    reason = f"\n\nReason: {p['reason']}" if p.get("reason") else ""
    return (
        f"Not approved: {p['student_name']} — {p['class_name']}",
        f"{p['student_name']}'s enrollment request for {p['class_name']} ({p['period_label']}) was not approved."
        f"{reason}\n\nIf you think this is a mistake, please contact the school office." + SIGNATURE,
    )


def _waitlist_promoted(p: dict[str, Any]) -> tuple[str, str]:
    lines = [
        f"A seat opened up: {p['student_name']} moved off the waitlist into {p['class_name']} ({p['period_label']})."
    ]
    if p.get("from_class_name"):
        lines.append(f"Because this was a higher choice, they were moved out of {p['from_class_name']}.")
    lines.append(
        "This enrollment is already approved."
        if p.get("status") == "approved"
        else "This enrollment is pending until the school approves it."
    )
    if p.get("pruned"):
        lines.append(
            "They were also taken off these lower-ranked waitlists in the same period: " + ", ".join(p["pruned"]) + "."
        )
    return (f"Off the waitlist: {p['student_name']} — {p['class_name']}", "\n\n".join(lines) + SIGNATURE)


def _enrollment_removed(p: dict[str, Any]) -> tuple[str, str]:
    return (
        f"Removed from class: {p['student_name']} — {p['class_name']}",
        f"The school removed {p['student_name']} from {p['class_name']} ({p['period_label']}).\n\n"
        "Please contact the school office if you have questions." + SIGNATURE,
    )


def _class_cancelled(p: dict[str, Any]) -> tuple[str, str]:
    what = "waitlist entry" if p.get("waitlisted") else "enrollment"
    return (
        f"Class cancelled: {p['class_name']}",
        f"{p['class_name']} ({p['period_label']}) has been removed from the schedule, so "
        f"{p['student_name']}'s {what} for it was cancelled.\n\n"
        f"You can choose another class at {get_settings().app_base_url}." + SIGNATURE,
    )


TEMPLATES: dict[str, Callable[[dict[str, Any]], tuple[str, str]]] = {
    "signup_code": _signup_code,
    "reset_code": _reset_code,
    "account_exists": _account_exists,
    "account_invite": _account_invite,
    "enrollment_approved": _enrollment_approved,
    "enrollment_rejected": _enrollment_rejected,
    "waitlist_promoted": _waitlist_promoted,
    "enrollment_removed": _enrollment_removed,
    "class_cancelled": _class_cancelled,
}


def render(template: str, params: dict[str, Any]) -> tuple[str, str]:
    return TEMPLATES[template](params)
