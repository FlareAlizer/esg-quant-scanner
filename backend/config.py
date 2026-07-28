"""Settings and TLS bootstrap.

Secrets come from the environment or a .env file in the repo root, never from
source. See .env.example.
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    # dotenv is optional: without it we just read os.environ.
    from dotenv import load_dotenv

    # .env lives one level up, in the repo root.
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:  # pragma: no cover
    pass


# ssl reads SSL_CERT_FILE; requests and curl_cffi (yfinance's engine) read the
# other two.
_CA_ENV_VARS = ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE")


def _windows_short_path(path: Path) -> Path | None:
    """The 8.3 form of a path, which is always ASCII.

    None if short names are disabled on the volume or the API isn't there.
    """
    import ctypes

    buffer = ctypes.create_unicode_buffer(4096)
    if not ctypes.windll.kernel32.GetShortPathNameW(str(path), buffer, 4096):
        return None

    candidate = Path(buffer.value)
    if not buffer.value.isascii() or not candidate.is_file():
        return None
    return candidate


def _copy_to_ascii_dir(bundle: Path) -> Path | None:
    """Copy cacert.pem into the first writable ASCII directory.

    Fallback for volumes with 8.3 names disabled. Copied once; later runs find it
    already there.
    """
    candidates = [
        Path(os.getenv("ProgramData", r"C:\ProgramData")) / "esg-quant-scanner",
        Path(os.getenv("SystemDrive", "C:") + "\\") / "Temp" / "esg-quant-scanner",
    ]

    for directory in candidates:
        if not str(directory).isascii():
            continue
        try:
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / "cacert.pem"
            # Refresh if the original is newer, since pip updates certifi.
            if not target.is_file() or target.stat().st_mtime < bundle.stat().st_mtime:
                shutil.copyfile(bundle, target)
            return target
        except OSError as exc:
            logger.debug("Каталог %s не подошёл для копии сертификатов: %s", directory, exc)

    return None


def ensure_ca_bundle() -> str | None:
    """Make sure the CA bundle sits at an ASCII path.

    yfinance goes through curl_cffi, and libcurl opens the certificate file with
    the Windows ANSI API. With a Cyrillic username the default certifi path
    (C:\\Users\\<кириллица>\\...\\certifi\\cacert.pem) can't be opened and every
    request dies with `curl: (77) error setting certificate verify locations`.
    From the outside it looks like Yahoo is refusing to serve data: the whole
    universe comes back with nulls and the pipeline finishes without a number in
    it.

    Fix is to point at the same file via an ASCII path, first through the 8.3
    short name (no copying), then through a copy in an ASCII directory. What we
    do not do is disable verification: an earlier version swallowed the error and
    turned TLS checking off, which traded a broken path for a MITM hole. If no
    ASCII path can be found we warn and leave the environment alone.
    """
    # An explicit setting always wins.
    for var in _CA_ENV_VARS:
        if os.getenv(var):
            return os.environ[var]

    if os.name != "nt":
        return None

    try:
        import certifi
    except ImportError:  # pragma: no cover
        return None

    bundle = Path(certifi.where())
    if str(bundle).isascii():
        return None  # plain ASCII path, nothing to fix

    resolved = _windows_short_path(bundle) or _copy_to_ascii_dir(bundle)
    if resolved is None:
        logger.warning(
            "Путь к сертификатам содержит не-ASCII символы (%s), и ASCII-альтернативу "
            "найти не удалось. Загрузка рыночных данных, скорее всего, будет падать "
            "с curl error 77. Задайте SSL_CERT_FILE вручную.",
            bundle,
        )
        return None

    for var in _CA_ENV_VARS:
        os.environ[var] = str(resolved)

    logger.debug("CA-бандл подменён на ASCII-путь: %s", resolved)
    return str(resolved)


def _env_float(name: str, default: float) -> float:
    """Read a float from the environment, falling back to default on junk."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """Built once at import."""

    # OpenAI-compatible endpoint: vsegpt, openrouter, openai
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    llm_base_url: str = field(
        default_factory=lambda: os.getenv("LLM_BASE_URL", "https://api.vsegpt.ru/v1")
    )
    llm_model: str = field(
        default_factory=lambda: os.getenv("LLM_MODEL_NAME", "deepseek/deepseek-r1-alt")
    )
    llm_timeout_s: float = field(default_factory=lambda: _env_float("LLM_TIMEOUT_S", 90.0))
    llm_max_retries: int = field(default_factory=lambda: _env_int("LLM_MAX_RETRIES", 3))

    # Risk-free rate for Sharpe and Sortino. Moves with the market, so it lives
    # here rather than inside the formulas.
    risk_free_rate: float = field(default_factory=lambda: _env_float("RISK_FREE_RATE", 0.04))
    # Annualisation constant.
    trading_days: int = 252

    # A fixed seed makes Monte Carlo runs reproducible. Set RANDOM_SEED="" for
    # varying draws.
    random_seed: int | None = field(
        default_factory=lambda: _env_int("RANDOM_SEED", 42) if os.getenv("RANDOM_SEED", "42") else None
    )

    @property
    def llm_enabled(self) -> bool:
        """Without a key the pipeline still runs, just degraded."""
        return bool(self.llm_api_key)


settings = Settings()

# Runs at import, before the first network call. yfinance and openai build their
# HTTP clients lazily, so the environment variables land in time.
ensure_ca_bundle()
