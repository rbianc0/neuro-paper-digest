from neuro_digest.delivery import SMTPConfig, SMTPEmailSender


class FakeSMTP:
    instance = None

    def __init__(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.calls = []
        self.message = None
        FakeSMTP.instance = self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def ehlo(self):
        self.calls.append("ehlo")

    def starttls(self, *, context):
        assert context is not None
        self.calls.append("starttls")

    def login(self, username, password):
        self.calls.append(("login", username, password))

    def send_message(self, message):
        self.message = message
        self.calls.append("send_message")


def test_smtp_sender_uses_starttls_and_deterministic_digest_message_id():
    config = SMTPConfig(
        host="smtp.gmail.com",
        port=587,
        username="neurofeed.test@gmail.com",
        password="app-password",
        from_address="Neurofeed <neurofeed.test@gmail.com>",
    )
    sender = SMTPEmailSender(config, smtp_factory=FakeSMTP)

    result = sender.send(
        to_address="scientist@example.org",
        subject="Neurofeed Weekly",
        html="<p>Hello</p>",
        text="Hello",
        digest_id="11111111-2222-3333-4444-555555555555",
    )

    smtp = FakeSMTP.instance
    assert smtp.host == "smtp.gmail.com"
    assert smtp.port == 587
    assert smtp.calls == [
        "ehlo",
        "starttls",
        ("login", "neurofeed.test@gmail.com", "app-password"),
        "ehlo",
        "send_message",
    ]
    assert smtp.message["To"] == "scientist@example.org"
    assert smtp.message["From"] == "Neurofeed <neurofeed.test@gmail.com>"
    assert smtp.message["X-Neurofeed-Digest-ID"] == "11111111-2222-3333-4444-555555555555"
    assert result.provider == "smtp"
    assert result.message_id == "<neurofeed-11111111-2222-3333-4444-555555555555@gmail.com>"


def test_smtp_config_defaults_to_gmail(monkeypatch):
    monkeypatch.setenv("NEUROFEED_SMTP_USERNAME", "neurofeed@gmail.com")
    monkeypatch.setenv("NEUROFEED_SMTP_PASSWORD", "secret")
    monkeypatch.delenv("NEUROFEED_SMTP_HOST", raising=False)
    monkeypatch.delenv("NEUROFEED_SMTP_PORT", raising=False)
    monkeypatch.delenv("NEUROFEED_EMAIL_FROM", raising=False)

    config = SMTPConfig.from_env()
    assert config.host == "smtp.gmail.com"
    assert config.port == 587
    assert config.from_address == "Neurofeed <neurofeed@gmail.com>"
