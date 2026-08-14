"""Transactional email delivery — a swappable seam.

Routes inject `Mailer = Depends(get_mailer)`; tests override it with a fake
that captures `raw_token`, making the verify/reset lifecycle fully testable
end-to-end (the raw token is a structured argument, not text inside a body).
"""
from typing import Protocol

import resend

from config import EMAIL_FROM, RESEND_API_KEY
from models import VerificationTokenType


class Mailer(Protocol):
    def __call__(
        self, *, to: str, token_type: VerificationTokenType, raw_token: str
    ) -> None: ...


_SUBJECTS = {
    VerificationTokenType.email_verification: "Verify your email",
    VerificationTokenType.password_reset: "Reset your password",
}


def resend_mailer(
    *, to: str, token_type: VerificationTokenType, raw_token: str
) -> None:
    if not RESEND_API_KEY:
        print(f"[EMAIL STUB] To: {to}, type: {token_type.value}")
        return

    resend.api_key = RESEND_API_KEY
    resend.Emails.send(
        {
            "from": EMAIL_FROM,
            "to": to,
            "subject": _SUBJECTS[token_type],
            "html": f"Your {token_type.value} token: {raw_token}",
        }
    )