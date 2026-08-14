"""Mail delivery is best-effort: a provider outage must never 500 the request."""
import pytest

from models import VerificationTokenType
from services.auth_service import _deliver_mail, register_user
from services.emailer import resend_mailer


class TestResendMailer:
    def test_stub_when_no_api_key(self, monkeypatch, capsys):
        monkeypatch.setattr("services.emailer.RESEND_API_KEY", "")
        resend_mailer(
            to="a@b.com",
            token_type=VerificationTokenType.email_verification,
            raw_token="tok",
        )
        out = capsys.readouterr().out
        assert "[EMAIL STUB]" in out

    def test_success_sends_via_resend(self, monkeypatch):
        monkeypatch.setattr("services.emailer.RESEND_API_KEY", "re_test")
        sent = {}

        def fake_send(payload):
            sent.update(payload)

        monkeypatch.setattr("services.emailer.resend.Emails.send", fake_send)
        resend_mailer(
            to="a@b.com",
            token_type=VerificationTokenType.password_reset,
            raw_token="tok",
        )
        assert sent["to"] == "a@b.com"
        assert "tok" in sent["html"]


class TestDeliverMail:
    def test_swallows_mailer_failure_and_logs(self, capsys):
        def boom(**kwargs):
            raise RuntimeError("api.resend.com read timed out")

        _deliver_mail(
            boom,
            to="a@b.com",
            token_type=VerificationTokenType.email_verification,
            raw_token="tok",
        )  # must not raise

        assert "[EMAIL ERROR]" in capsys.readouterr().err

    def test_passes_through_on_success(self, capsys):
        sent = {}

        def fake(**kwargs):
            sent.update(kwargs)

        _deliver_mail(
            fake,
            to="a@b.com",
            token_type=VerificationTokenType.password_reset,
            raw_token="tok",
        )
        assert sent["raw_token"] == "tok"
        assert capsys.readouterr().err == ""


class TestRegisterSurvivesMailFailure:
    def test_register_returns_201_when_email_send_raises(self, client):
        from main import app
        from deps import get_mailer

        def boom(**kwargs):
            raise RuntimeError("read timed out")

        app.dependency_overrides[get_mailer] = lambda: boom
        try:
            resp = client.post(
                "/auth/register", json={"email": "a@b.com", "password": "pass123"}
            )
            assert resp.status_code == 201, resp.text
            assert resp.json()["email"] == "a@b.com"
        finally:
            app.dependency_overrides.pop(get_mailer, None)