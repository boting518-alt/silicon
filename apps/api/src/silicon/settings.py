import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    database_url: str = field(repr=False)
    environment: str = "development"

    oidc_issuer: str = ""
    oidc_client_id: str = "silicon-web"
    oidc_client_secret: str = field(default="", repr=False)
    public_origin: str = "https://localhost:5173"
    session_seconds: int = 1800
    oidc_ca_bundle: str = ""

    def __post_init__(self):
        if self.environment not in {"development", "test"}:
            raise ValueError("Only development/test supported; production hardening and operational readiness are not accepted")
        if not self.database_url.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must use postgresql+psycopg")

        from urllib.parse import urlsplit
        origin = urlsplit(self.public_origin)
        if origin.scheme != "https" or not origin.netloc or origin.path or origin.query or origin.fragment:
            raise ValueError("PUBLIC_ORIGIN must be an HTTPS origin without path")
        if self.oidc_issuer:
            issuer = urlsplit(self.oidc_issuer)
            if issuer.scheme != "https" and not (issuer.scheme == "http" and issuer.hostname in {"localhost", "127.0.0.1"}):
                raise ValueError("OIDC issuer must be HTTPS (loopback HTTP allowed for development IdP)")
        if not 60 <= self.session_seconds <= 3600:
            raise ValueError("session lifetime must be 60..3600 seconds")

    @classmethod
    def from_env(cls):
        return cls(os.environ["DATABASE_URL"], os.getenv("SILICON_ENV", "development"),
                   os.getenv("OIDC_ISSUER", ""), os.getenv("OIDC_CLIENT_ID", "silicon-web"),
                   os.getenv("OIDC_CLIENT_SECRET", ""), os.getenv("PUBLIC_ORIGIN", "https://localhost:5173"),
                   oidc_ca_bundle=os.getenv("OIDC_CA_BUNDLE", ""))
