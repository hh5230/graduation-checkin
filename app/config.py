"""Environment-backed configuration, evaluated for each application factory call."""

import os
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = "postgresql+psycopg://grad:grad@localhost:5434/graduation"


class Config:
    TESTING = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    def __init__(self):
        load_dotenv(ROOT / ".env")
        self.SECRET_KEY = os.environ["SECRET_KEY"]
        self.SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", DEFAULT_DB)
        self.REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6380/0")
        self.STATS_CACHE_TTL = int(os.getenv("STATS_CACHE_TTL", "10"))
        self.CLAIM_RATE_LIMIT = int(os.getenv("CLAIM_RATE_LIMIT", "10"))
        self.CLAIM_RATE_WINDOW = int(os.getenv("CLAIM_RATE_WINDOW", "600"))
        if self.CLAIM_RATE_LIMIT < 0 or self.CLAIM_RATE_WINDOW <= 0:
            raise ValueError("CLAIM_RATE_LIMIT must be nonnegative and CLAIM_RATE_WINDOW positive")
        self.SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "").strip().lower() in {"1", "true", "yes"}
        self.TRUST_PROXY = os.getenv("TRUST_PROXY", "").strip().lower() in {"1", "true", "yes"}
        self.PROXY_HOPS = int(os.getenv("PROXY_HOPS", "1"))
        self.PREFERRED_URL_SCHEME = "https" if self.SESSION_COOKIE_SECURE else "http"
        self.SOCKETIO_ASYNC_MODE = os.getenv("SOCKETIO_ASYNC_MODE", "threading")
        cert_dir = "certs" if ROOT == Path("/opt/graduation-checkin") else "deploy"
        self.CA_CERT_PATH = os.getenv("CA_CERT_PATH", str(ROOT / cert_dir / "ca.crt"))
        self.SHOW_CA_LINK = os.getenv("SHOW_CA_LINK", "").strip().lower() in {"1", "true", "yes"}
        self.HOST = os.getenv("HOST", "0.0.0.0")
        self.PORT = int(os.getenv("PORT", "5001"))


class TestConfig(Config):
    TESTING = True

    def __init__(self):
        super().__init__()
        self.SESSION_COOKIE_SECURE = False
        self.PREFERRED_URL_SCHEME = "http"
        self.SOCKETIO_ASYNC_MODE = "threading"
        self.SQLALCHEMY_DATABASE_URI = os.getenv("TEST_DATABASE_URL", DEFAULT_DB + "_test")
        # Keep the same cache key in both environments without mixing their counts.
        url = urlsplit(self.REDIS_URL)
        options = dict(parse_qsl(url.query))
        production_db = options.get("db", url.path.strip("/") or "0")
        options["db"] = "1" if production_db != "1" else "0"
        self.REDIS_URL = os.getenv("TEST_REDIS_URL") or url._replace(query=urlencode(options)).geturl()
