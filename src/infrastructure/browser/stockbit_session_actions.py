"""
Stockbit CLI session management actions (login, browse, spy, status).

Layer: Infrastructure
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from src.infrastructure.browser.stockbit_browser_context import (
    LOGIN_URL,
    ORDER_BOOK_URL,
    ORDERBOOK_PAGE_URL,
    SCREENER_URL,
    STREAM_URL,
    _persistent_context,
    _require_playwright,
    default_stockbit_profile_dir,
)
from src.infrastructure.browser.stockbit_token_extractor import (
    _intercept_token,
    _resolve_token,
)
from src.infrastructure.browser.stockbit_token_store import StockbitTokenStore
from src.infrastructure.config.stockbit_config import (
    StockbitConfig,
    load_stockbit_config,
)

if TYPE_CHECKING:
    from src.application.services.stockbit_session import StockbitSessionStatus

logger = logging.getLogger(__name__)

# Auth URL fragments shared by login + reauth (Stockbit SPA paths).
_AUTH_FLOW_FRAGMENTS = (
    "/login",
    "/register",
    "/forgot",
    "/verify",
    "/otp",
    "/2fa",
    "/two-factor",
    "/email-verification",
    "/phone-verification",
    "/trusted-device",
)

# Button labels for the common Stockbit re-auth click path (EN + ID).
_LOGIN_BUTTON_NAME = re.compile(r"^\s*(log\s*in|login|masuk|sign\s*in)\s*$", re.I)
_CONFIRM_BUTTON_NAME = re.compile(
    r"^\s*(ok|okay|ya|yes|confirm|lanjutkan|continue|setuju|mengerti|tutup)\s*$",
    re.I,
)


@dataclass(frozen=True)
class StockbitReauthResult:
    """Outcome of Stockbit reauth / JWT refresh."""

    success: bool
    token_saved: bool
    already_authenticated: bool
    auto_clicks: tuple[str, ...]
    message: str
    mode: str = "headed"


ReauthMode = Literal["headless", "headed"]

# Headless JWT capture is flaky under cron (SPA request timing / URL heuristics).
# Retry a few times with a slightly longer settle; never print token material.
_HEADLESS_MAX_ATTEMPTS = 3
_HEADLESS_RETRY_PAUSE_S = 0.75
_HEADLESS_RETRY_EXTRA_SETTLE_MS = 2_000


@dataclass(frozen=True)
class HeadlessCaptureDiag:
    """Non-secret facts about one headless JWT capture attempt."""

    attempt: int
    max_attempts: int
    page_url: str
    settle_ms: int
    token_present: bool
    algorithm: str | None
    token_state: str | None
    valid_rs256: bool
    logged_in: bool
    on_auth: bool
    reason: str

    def format_lines(self) -> tuple[str, ...]:
        token_bit = (
            f"present alg={self.algorithm or '?'} state={self.token_state or '?'}"
            if self.token_present
            else "absent"
        )
        return (
            f"  Attempt {self.attempt}/{self.max_attempts} "
            f"settle_ms={self.settle_ms} reason={self.reason}",
            f"  url={self.page_url or '(empty)'}",
            f"  token={token_bit} valid_rs256={self.valid_rs256}",
            f"  logged_in={self.logged_in} on_auth={self.on_auth}",
        )


def _classify_headless_capture(
    *,
    attempt: int,
    max_attempts: int,
    page_url: str,
    settle_ms: int,
    token: str | None,
    valid_rs256: bool,
    algorithm: str | None,
    token_state: str | None,
    logged_in: bool,
    on_auth: bool,
) -> HeadlessCaptureDiag:
    """Classify a headless capture without requiring a successful URL heuristic."""
    if valid_rs256 and token:
        if on_auth:
            reason = "ok_rs256_on_auth_url"
        elif not logged_in:
            reason = "ok_rs256_ambiguous_url"
        else:
            reason = "ok_rs256"
    elif on_auth:
        reason = "auth_ui"
    elif not token:
        reason = "no_token_intercepted"
    elif algorithm and algorithm != "RS256":
        reason = f"token_not_rs256(alg={algorithm})"
    elif token_state and token_state != "valid":
        reason = f"token_{token_state}"
    else:
        reason = "token_not_valid_rs256"

    return HeadlessCaptureDiag(
        attempt=attempt,
        max_attempts=max_attempts,
        page_url=page_url or "",
        settle_ms=settle_ms,
        token_present=bool(token),
        algorithm=algorithm,
        token_state=token_state,
        valid_rs256=bool(valid_rs256 and token),
        logged_in=logged_in,
        on_auth=on_auth,
        reason=reason,
    )


def _reauth_wall_clock() -> str:
    """Local wall clock for cron logs (no dependency on operator TZ env)."""
    from datetime import datetime

    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")


def _url_looks_logged_in(url: str) -> bool:
    """True when URL is on stockbit.com and outside the auth flow paths."""
    if "stockbit.com" not in (url or ""):
        return False
    lower = url.lower()
    return not any(fragment in lower for fragment in _AUTH_FLOW_FRAGMENTS)


def _url_looks_auth_flow(url: str) -> bool:
    lower = (url or "").lower()
    return any(fragment in lower for fragment in _AUTH_FLOW_FRAGMENTS)


def _save_rs256_token_if_valid(*, profile_dir: Path, token: str | None) -> bool:
    """Persist token only when it is a locally valid RS256 Exodus JWT."""
    if not token:
        return False
    token_store = StockbitTokenStore(profile_dir / "token.json")
    candidate = token_store.describe_candidate(token)
    if candidate.state == "valid" and candidate.algorithm == "RS256":
        token_store.save(token)
        return True
    return False


def _mark_profile_logged_in(profile_dir: Path) -> None:
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / ".logged_in_at").write_text(str(time.time()))


def _try_click_role_button(page: Any, name_pattern: re.Pattern[str], *, timeout_ms: int) -> bool:
    """Click first visible role=button whose accessible name matches pattern."""
    try:
        buttons = page.get_by_role("button")
        count = buttons.count()
    except Exception:
        return False
    for i in range(min(count, 40)):
        try:
            btn = buttons.nth(i)
            if not btn.is_visible(timeout=200):
                continue
            label = (btn.inner_text(timeout=200) or "").strip()
            if not label:
                try:
                    label = (btn.get_attribute("aria-label") or "").strip()
                except Exception:
                    label = ""
            if not name_pattern.match(label):
                continue
            btn.click(timeout=timeout_ms)
            return True
        except Exception:
            continue
    return False


def _try_click_text_button(page: Any, texts: tuple[str, ...], *, timeout_ms: int) -> bool:
    for text in texts:
        try:
            loc = page.get_by_role("button", name=re.compile(rf"^\s*{re.escape(text)}\s*$", re.I))
            if loc.count() > 0 and loc.first.is_visible(timeout=timeout_ms):
                loc.first.click(timeout=timeout_ms)
                return True
        except Exception:
            continue
        try:
            loc = page.locator(f'button:has-text("{text}")')
            if loc.count() > 0 and loc.first.is_visible(timeout=timeout_ms):
                loc.first.click(timeout=timeout_ms)
                return True
        except Exception:
            continue
    return False


def _nudge_password_autofill(page: Any) -> None:
    """Focus common credential fields so browser autofill can populate them."""
    for selector in (
        'input[type="email"]',
        'input[type="text"]',
        'input[name="username"]',
        'input[name="email"]',
        'input[type="password"]',
    ):
        try:
            loc = page.locator(selector).first
            if loc.count() > 0 and loc.is_visible(timeout=300):
                loc.click(timeout=500)
                page.wait_for_timeout(200)
        except Exception:
            continue


def attempt_stockbit_reauth_clicks(page: Any) -> tuple[str, ...]:
    """
    Best-effort UI automation for the usual human reauth path:
    autofill nudge → Login/Masuk → OK/Confirm on popup.

    Always headed; selectors are fail-soft. Returns labels of successful clicks.
    """
    clicks: list[str] = []
    _nudge_password_autofill(page)
    try:
        page.wait_for_timeout(400)
    except Exception:
        pass

    if _try_click_role_button(page, _LOGIN_BUTTON_NAME, timeout_ms=2_500) or _try_click_text_button(
        page,
        ("Login", "Log in", "Masuk", "Sign in"),
        timeout_ms=2_500,
    ):
        clicks.append("login")
        try:
            page.wait_for_timeout(1_200)
        except Exception:
            pass

    # Confirmation / device-trust style dialog (may appear after login).
    for _ in range(3):
        if _try_click_role_button(
            page, _CONFIRM_BUTTON_NAME, timeout_ms=2_000
        ) or _try_click_text_button(
            page,
            ("OK", "Ok", "Ya", "Yes", "Confirm", "Lanjutkan", "Continue", "Setuju", "Mengerti"),
            timeout_ms=2_000,
        ):
            clicks.append("confirm")
            try:
                page.wait_for_timeout(800)
            except Exception:
                pass
        else:
            break

    return tuple(clicks)


def _capture_exodus_token_from_page(
    page: Any,
    token_box: list[str],
    *,
    cfg: StockbitConfig,
) -> str | None:
    try:
        page.goto(ORDERBOOK_PAGE_URL, timeout=cfg.nav_timeout_ms, wait_until="domcontentloaded")
        page.wait_for_timeout(cfg.spa_settle_ms)
    except Exception as e:
        logger.debug("Orderbook navigation for JWT capture failed: %s", e)
    return _resolve_token(page, token_box)


# ── Spy target pages ───────────────────────────────────────────────────────
_STOCK_BROKER_PAGE_URL = "https://stockbit.com/broker-analysis/stock"
_BROKER_ANALYSIS_PAGE_URL = "https://stockbit.com/broker-analysis/broker"

_MOVERS_URL_PATTERNS = [
    "exodus.stockbit.com/screener",
    "exodus.stockbit.com/market/mover",
    "exodus.stockbit.com/pre-open",
    "exodus.stockbit.com/iev",
    "exodus.stockbit.com/stock/mover",
    "mover",
    "iev",
    "preopen",
]
_ORDERBOOK_URL_PATTERNS = [
    "company-price-feed/v2/orderbook",
    "exodus.stockbit.com/orderbook",
    "exodus.stockbit.com/order-book",
    "exodus.stockbit.com/stock",
    "orderbook",
    "order-book",
]
_BROKER_URL_PATTERNS = ["marketdetectors", "broker/activity", "activity/historical"]


def _url_matches(url: str, patterns: list[str]) -> bool:
    url_lower = url.lower()
    return any(p in url_lower for p in patterns)


def save_stockbit_session(
    profile_dir: Path | None = None,
    timeout: int = 300,
    *,
    stockbit_config: StockbitConfig | None = None,
) -> None:
    """
    Launch headed Chromium for manual Stockbit login.

    Uses a persistent browser profile (.stockbit_profile/) so all browser
    state (cookies, localStorage, IndexedDB) is preserved across runs.
    The browser stays logged in exactly like a regular Chrome profile.

    Args:
        profile_dir: Persistent browser profile directory
        timeout: Seconds to wait for login completion
    """
    profile_dir = profile_dir or default_stockbit_profile_dir()
    cfg = stockbit_config or load_stockbit_config()
    sync_playwright = _require_playwright()

    print("Opening Stockbit login page in a browser window.")
    print(f"Please log in manually. You have {timeout} seconds.")
    if timeout < 180:
        print("Tip: use --timeout 300 if you have 2FA enabled.")
    print(f"Browser profile: {profile_dir}  (stays logged in across runs)\n")

    with sync_playwright() as pw:
        ctx, page = _persistent_context(pw, profile_dir, headless=False)
        # Register before navigation so any Exodus Bearer token sent during or
        # after login is captured — never inferred from URL/page content.
        token_box = _intercept_token(page)
        page.goto(LOGIN_URL, timeout=cfg.nav_timeout_ms, wait_until="domcontentloaded")

        logged_in = False

        print("Waiting for login to complete (including 2FA if enabled)...")
        print(f"  Current page: {LOGIN_URL}\n")

        try:
            page.wait_for_url(_url_looks_logged_in, timeout=timeout * 1_000)
            print(f"  Logged in → {page.url}")
            page.wait_for_timeout(2_000)
            logged_in = True
        except Exception as e:
            if "Timeout" in str(e):
                print(f"\nTimeout reached ({timeout}s). Last URL: {page.url}")
            else:
                print(f"\nLogin detection error: {e}")

        token: str | None = None
        if logged_in:
            page.wait_for_timeout(3_000)
            token = _capture_exodus_token_from_page(page, token_box, cfg=cfg)

        ctx.close()

        if logged_in:
            _mark_profile_logged_in(profile_dir)
            print(
                f"\nSession saved → {profile_dir}/\n"
                f"  The browser profile stores all cookies and tokens.\n"
                f"  It will stay logged in across runs (like a Chrome profile)."
            )

            token_saved = _save_rs256_token_if_valid(profile_dir=profile_dir, token=token)
            if token_saved:
                print("  Exodus API JWT captured and saved.")
            else:
                print(
                    "  Warning: could not capture a usable Exodus API JWT from this login.\n"
                    "  The browser profile is saved; the token will be refreshed"
                    " automatically on the next API call."
                )
            print("Run 'saham fetch stockbit status' to verify.")
            print("Run 'saham fetch stockbit spy' to discover API endpoints.")
        else:
            print("\nTimeout — login not detected. Session NOT saved.")
            print(
                "Run 'saham fetch stockbit login' again and complete login within the time limit."
            )


def _require_existing_profile(profile_dir: Path) -> None:
    if not (profile_dir.exists() and any(profile_dir.iterdir())):
        raise RuntimeError(
            "No Stockbit profile found.\n"
            "Run: saham fetch stockbit login   # one-time manual bootstrap"
        )


def _try_capture_valid_jwt_from_orderbook(
    *,
    page: Any,
    token_box: list[str],
    profile_dir: Path,
    cfg: StockbitConfig,
    settle_ms: int | None = None,
) -> tuple[str | None, bool, str | None, str | None]:
    """
    Navigate orderbook and inspect any captured JWT.

    Returns ``(token, is_valid_rs256, algorithm, token_state)``. Never logs the
    token string. ``settle_ms`` overrides config SPA settle (used for retries).
    """
    wait_ms = cfg.spa_settle_ms if settle_ms is None else max(0, int(settle_ms))
    try:
        page.goto(ORDERBOOK_PAGE_URL, timeout=cfg.nav_timeout_ms, wait_until="domcontentloaded")
        page.wait_for_timeout(wait_ms)
    except Exception as e:
        logger.debug("Orderbook open for JWT capture failed: %s", e)
    token = _resolve_token(page, token_box)
    if not token:
        return None, False, None, None
    meta = StockbitTokenStore(profile_dir / "token.json").describe_candidate(token)
    valid = meta.state == "valid" and meta.algorithm == "RS256"
    return token, valid, meta.algorithm, meta.state


def reauth_stockbit_session(
    profile_dir: Path | None = None,
    timeout: int = 180,
    *,
    stockbit_config: StockbitConfig | None = None,
    mode: ReauthMode = "headless",
) -> StockbitReauthResult:
    """
    Refresh Exodus JWT from the persistent Stockbit browser profile.

    Modes
    -----
    ``headless`` (default, cron-safe)
        Open the profile without a window, hit orderbook, capture RS256 JWT.
        Retries a few times with diagnostics. No login UI automation and no
        human fallback. Fails closed if auth UI appears or no valid JWT is
        minted — run ``--mode headed`` then.

    ``headed``
        Visible Chromium for password autofill, confirmation dialogs, and
        optional manual login when cookies alone cannot mint a JWT.

    Requires an existing profile (``saham fetch stockbit login`` once first).
    """
    if mode not in ("headless", "headed"):
        raise ValueError(f"mode must be 'headless' or 'headed', got {mode!r}")

    profile_dir = profile_dir or default_stockbit_profile_dir()
    cfg = stockbit_config or load_stockbit_config()
    _require_existing_profile(profile_dir)

    if mode == "headless":
        return _reauth_headless_jwt_refresh(profile_dir=profile_dir, cfg=cfg)
    return _reauth_headed_interactive(profile_dir=profile_dir, timeout=timeout, cfg=cfg)


def _reauth_headless_jwt_refresh(
    *,
    profile_dir: Path,
    cfg: StockbitConfig,
    max_attempts: int = _HEADLESS_MAX_ATTEMPTS,
) -> StockbitReauthResult:
    """
    Cron path: headless only — mint JWT from cookies/session or fail closed.

    A locally valid RS256 JWT is sufficient for success (and is persisted) even
    when the final page URL is ambiguous. Auth UI still fails closed after
    retries so cron does not pretend a login dialog is recoverable headlessly.
    """
    attempts = max(1, int(max_attempts))
    started = _reauth_wall_clock()
    print(f"Stockbit JWT refresh (headless)  @ {started}")
    print(f"  Profile : {profile_dir}")
    print(f"  Attempts: {attempts} (extra settle +{_HEADLESS_RETRY_EXTRA_SETTLE_MS}ms after first)")
    print("  No UI — fails if login page appears; use --mode headed to recover.\n")

    sync_playwright = _require_playwright()
    last_diag: HeadlessCaptureDiag | None = None

    for attempt in range(1, attempts + 1):
        settle_ms = cfg.spa_settle_ms
        if attempt > 1:
            settle_ms = cfg.spa_settle_ms + _HEADLESS_RETRY_EXTRA_SETTLE_MS

        token: str | None = None
        valid = False
        algorithm: str | None = None
        token_state: str | None = None
        page_url = ""
        on_auth = False
        logged_in = False

        with sync_playwright() as pw:
            ctx, page = _persistent_context(pw, profile_dir, headless=True)
            try:
                token_box = _intercept_token(page)
                token, valid, algorithm, token_state = _try_capture_valid_jwt_from_orderbook(
                    page=page,
                    token_box=token_box,
                    profile_dir=profile_dir,
                    cfg=cfg,
                    settle_ms=settle_ms,
                )
                page_url = getattr(page, "url", "") or ""
                on_auth = _url_looks_auth_flow(page_url)
                logged_in = _url_looks_logged_in(page_url)
            finally:
                ctx.close()

        diag = _classify_headless_capture(
            attempt=attempt,
            max_attempts=attempts,
            page_url=page_url,
            settle_ms=settle_ms,
            token=token,
            valid_rs256=valid,
            algorithm=algorithm,
            token_state=token_state,
            logged_in=logged_in,
            on_auth=on_auth,
        )
        last_diag = diag
        for line in diag.format_lines():
            print(line)
        logger.info(
            "headless reauth attempt=%s/%s reason=%s url=%s valid_rs256=%s "
            "alg=%s state=%s logged_in=%s on_auth=%s",
            diag.attempt,
            diag.max_attempts,
            diag.reason,
            diag.page_url,
            diag.valid_rs256,
            diag.algorithm,
            diag.token_state,
            diag.logged_in,
            diag.on_auth,
        )

        if diag.valid_rs256 and token:
            token_saved = _save_rs256_token_if_valid(profile_dir=profile_dir, token=token)
            _mark_profile_logged_in(profile_dir)
            if diag.reason == "ok_rs256_ambiguous_url":
                msg = (
                    "Headless JWT refresh OK — RS256 saved "
                    "(page URL was ambiguous; token still valid)."
                )
            elif diag.reason == "ok_rs256_on_auth_url":
                msg = (
                    "Headless JWT refresh OK — RS256 saved "
                    "(captured while URL still looked like auth flow)."
                )
            else:
                msg = "Headless JWT refresh OK — already authenticated."
            print(f"✓ {msg}")
            return StockbitReauthResult(
                success=True,
                token_saved=token_saved,
                already_authenticated=True,
                auto_clicks=(),
                message=msg,
                mode="headless",
            )

        if attempt < attempts:
            print(f"  Retrying in {_HEADLESS_RETRY_PAUSE_S:.2f}s...")
            time.sleep(_HEADLESS_RETRY_PAUSE_S)

    reason = last_diag.reason if last_diag is not None else "unknown"
    human = {
        "auth_ui": "auth UI (login/OTP) — headless cannot complete this",
        "no_token_intercepted": "no Exodus Bearer intercepted from session",
    }.get(reason, reason)
    msg = (
        f"Headless JWT refresh failed after {attempts} attempt(s) ({human}). "
        "Run: saham fetch stockbit reauth --mode headed"
    )
    print(f"✗ {msg}")
    if last_diag is not None:
        print(f"  Last url={last_diag.page_url or '(empty)'} reason={last_diag.reason}")
    return StockbitReauthResult(
        success=False,
        token_saved=False,
        already_authenticated=False,
        auto_clicks=(),
        message=msg,
        mode="headless",
    )


def _reauth_headed_interactive(
    *,
    profile_dir: Path,
    timeout: int,
    cfg: StockbitConfig,
) -> StockbitReauthResult:
    """Interactive path: visible browser + auto-clicks + optional human finish."""
    print("Stockbit reauth (headed — UI recovery)")
    print(f"  Profile : {profile_dir}")
    print(f"  Timeout : {timeout}s (auto-clicks first; you can still finish manually)\n")

    sync_playwright = _require_playwright()
    auto_clicks: tuple[str, ...] = ()
    logged_in = False
    token: str | None = None

    with sync_playwright() as pw:
        ctx, page = _persistent_context(pw, profile_dir, headless=False)
        try:
            token_box = _intercept_token(page)
            token, valid, _alg, _state = _try_capture_valid_jwt_from_orderbook(
                page=page,
                token_box=token_box,
                profile_dir=profile_dir,
                cfg=cfg,
            )
            # Valid RS256 is enough to persist; URL heuristics are diagnostic only.
            if valid and token:
                token_saved = _save_rs256_token_if_valid(profile_dir=profile_dir, token=token)
                _mark_profile_logged_in(profile_dir)
                msg = "Already authenticated; Exodus JWT refreshed from browser session."
                print(f"✓ {msg}")
                return StockbitReauthResult(
                    success=True,
                    token_saved=token_saved,
                    already_authenticated=True,
                    auto_clicks=(),
                    message=msg,
                    mode="headed",
                )

            if _url_looks_auth_flow(page.url):
                print(f"  Auth UI detected ({page.url})")
                print(
                    "  Attempting Login / confirmation clicks (saved password if browser fills)..."
                )
                auto_clicks = attempt_stockbit_reauth_clicks(page)
                if auto_clicks:
                    print(f"  Auto-clicks: {', '.join(auto_clicks)}")
                else:
                    print("  No matching Login/OK buttons found — complete login in the window.")
            else:
                print("  No usable JWT yet; opening login page for reauth clicks...")
                try:
                    page.goto(LOGIN_URL, timeout=cfg.nav_timeout_ms, wait_until="domcontentloaded")
                    page.wait_for_timeout(800)
                except Exception as e:
                    logger.debug("Login page navigation during reauth failed: %s", e)
                auto_clicks = attempt_stockbit_reauth_clicks(page)
                if auto_clicks:
                    print(f"  Auto-clicks: {', '.join(auto_clicks)}")

            logged_in = _url_looks_logged_in(page.url)
            if not logged_in:
                print("  Waiting for session to leave auth flow (finish manually if needed)...")
                try:
                    page.wait_for_url(_url_looks_logged_in, timeout=timeout * 1_000)
                    logged_in = True
                    print(f"  Logged in → {page.url}")
                except Exception as e:
                    if "Timeout" in str(e):
                        print(f"\nTimeout ({timeout}s). Last URL: {page.url}")
                    else:
                        print(f"\nReauth wait error: {e}")

            token = None
            if logged_in:
                page.wait_for_timeout(1_500)
                token = _capture_exodus_token_from_page(page, token_box, cfg=cfg)
        finally:
            ctx.close()

    if not logged_in:
        msg = "Reauth failed — still on auth UI. Run: saham fetch stockbit login"
        print(f"\n✗ {msg}")
        return StockbitReauthResult(
            success=False,
            token_saved=False,
            already_authenticated=False,
            auto_clicks=auto_clicks,
            message=msg,
            mode="headed",
        )

    _mark_profile_logged_in(profile_dir)
    token_saved = _save_rs256_token_if_valid(profile_dir=profile_dir, token=token)
    if token_saved:
        msg = "Reauth OK — profile marked logged-in and Exodus JWT saved."
        print(f"\n✓ {msg}")
    else:
        msg = (
            "Reauth reached app UI but no usable RS256 JWT was captured; "
            "profile marked logged-in (JWT may refresh on next API call)."
        )
        print(f"\n⚠ {msg}")
    print("Verify: saham fetch stockbit status")
    return StockbitReauthResult(
        success=True,
        token_saved=token_saved,
        already_authenticated=False,
        auto_clicks=auto_clicks,
        message=msg,
        mode="headed",
    )


def _persist_newer_token(
    token_store: StockbitTokenStore, token_box: list[str], last_seen: int
) -> int:
    """
    Opportunistically persist a newly captured Exodus token.

    If token_box has grown since last_seen, evaluate the newest captured
    token and persist it only when StockbitTokenStore.is_worth_saving()
    accepts it (locally valid RS256 JWT, newer than what's stored). Returns
    the updated last_seen index so identical/rejected tokens are not
    re-evaluated on every loop tick.
    """
    if len(token_box) <= last_seen:
        return last_seen
    candidate = token_box[-1]
    if token_store.is_worth_saving(candidate):
        token_store.save(candidate)
        logger.info("Captured newer Stockbit Exodus token during browse — saved")
    return len(token_box)


def browse_stockbit_session(
    profile_dir: Path | None = None,
    url: str = STREAM_URL,
    *,
    stockbit_config: StockbitConfig | None = None,
) -> None:
    """
    Open a headed browser with the saved Stockbit session and keep it open.

    The persisted browser profile is authoritative for browsing. API-token
    expiry never blocks opening it: valid browser cookies may still issue a
    fresh JWT, which this session observes and persists opportunistically.

    While open, any newer Exodus Bearer token observed on normal browser
    requests is opportunistically saved (see _persist_newer_token). Page
    navigation alone is never treated as authentication proof.

    Args:
        profile_dir: Persistent browser profile directory
        url: Stockbit page to open (default: stream/home)
    """
    profile_dir = profile_dir or default_stockbit_profile_dir()
    cfg = stockbit_config or load_stockbit_config()

    if not (profile_dir.exists() and any(profile_dir.iterdir())):
        raise RuntimeError("No Stockbit profile found.\nRun: saham fetch stockbit login")

    sync_playwright = _require_playwright()
    token_store = StockbitTokenStore(profile_dir / "token.json")
    print(f"Using persistent profile: {profile_dir}/")
    print(f"Opening {url}")
    print("The browser will stay open until you press Ctrl+C.\n")

    with sync_playwright() as pw:
        ctx, page = _persistent_context(pw, profile_dir, headless=False)
        token_box = _intercept_token(page)
        page.goto(url, timeout=cfg.nav_timeout_ms, wait_until="domcontentloaded")

        last_seen = 0
        try:
            while True:
                page.wait_for_timeout(10_000)
                last_seen = _persist_newer_token(token_store, token_box, last_seen)
        except KeyboardInterrupt:
            print("\nClosing browser...")
        finally:
            _persist_newer_token(token_store, token_box, last_seen)
            ctx.close()


def spy_stockbit_session(
    profile_dir: Path | None = None,
    target: str = "screener",
    ticker: str = "BBCA",
    output_file: Path = Path("journals/stockbit-spy.json"),
    settle_ms: int = 6_000,
    *,
    stockbit_config: StockbitConfig | None = None,
) -> dict:
    """
    Open Stockbit with the saved session, capture ALL API responses.

    Saves full request/response log to output_file for analysis.
    Use this to identify the correct API endpoints for movers and order book.

    Args:
        profile_dir: Persistent browser profile directory
        target: 'screener', 'orderbook', 'stock', 'stock-profile', 'broker-scan'
        ticker: Ticker to use for orderbook/stock target
        output_file: Where to save captured requests
        settle_ms: Milliseconds to wait for SPA to settle

    Returns:
        Summary dict with total_responses, unique_urls, output_file path
    """
    profile_dir = profile_dir or default_stockbit_profile_dir()
    cfg = stockbit_config or load_stockbit_config()

    if not (profile_dir.exists() and any(profile_dir.iterdir())):
        raise RuntimeError("No Stockbit profile found.\nRun: saham fetch stockbit login")

    sync_playwright = _require_playwright()

    if target == "orderbook":
        url = ORDER_BOOK_URL.format(ticker=ticker.upper())
    elif target == "stock":
        url = _STOCK_BROKER_PAGE_URL
    elif target == "stock-profile":
        url = f"https://stockbit.com/stocks/{ticker.upper()}"
    elif target == "broker-scan":
        url = _BROKER_ANALYSIS_PAGE_URL
    elif target == "broker":
        url = _STOCK_BROKER_PAGE_URL
    else:
        url = SCREENER_URL

    captured: list[dict] = []

    with sync_playwright() as pw:
        ctx, page = _persistent_context(pw, profile_dir, headless=False)

        def on_response(response):
            ct = response.headers.get("content-type", "")
            entry: dict = {
                "url": response.url,
                "status": response.status,
                "content_type": ct,
                "body": None,
            }
            if "json" in ct:
                try:
                    entry["body"] = response.json()
                except Exception:
                    entry["body"] = "<parse error>"
            captured.append(entry)

        page.on("response", on_response)

        print(f"\nNavigating to: {url}")
        print(f"Capturing all network responses for {settle_ms // 1000}s...")
        print("The browser will open visibly so you can interact if needed.")
        print("Press Ctrl+C to stop early.\n")

        try:
            page.goto(url, timeout=cfg.nav_timeout_ms, wait_until="domcontentloaded")
            page.wait_for_timeout(settle_ms)
        except KeyboardInterrupt:
            pass
        finally:
            ctx.close()

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(captured, f, indent=2, default=str)

    json_responses = [c for c in captured if "json" in c.get("content_type", "")]
    unique_urls = sorted(set(c["url"] for c in json_responses))

    movers_hits = [u for u in unique_urls if _url_matches(u, _MOVERS_URL_PATTERNS)]
    orderbook_hits = [u for u in unique_urls if _url_matches(u, _ORDERBOOK_URL_PATTERNS)]
    broker_hits = [u for u in unique_urls if _url_matches(u, _BROKER_URL_PATTERNS)]

    return {
        "total_responses": len(captured),
        "json_responses": len(json_responses),
        "unique_json_urls": unique_urls,
        "movers_candidates": movers_hits,
        "orderbook_candidates": orderbook_hits,
        "broker_candidates": broker_hits,
        "output_file": str(output_file),
    }


def get_stockbit_session_status(profile_dir: Path | None = None) -> StockbitSessionStatus:
    """
    Compose a read-only Stockbit authentication-health snapshot.

    Never opens a browser or makes a network call. Reads two independent
    facts — the browser-profile login marker (informational age only) and
    the persisted JWT's local validity via StockbitTokenStore — and reports
    them separately rather than collapsing them into a single pass/fail
    signal. Returns the application-layer StockbitSessionStatus DTO;
    infrastructure is allowed to depend inward on that shape.
    """
    from src.application.services.stockbit_session import StockbitSessionStatus

    profile_dir = profile_dir or default_stockbit_profile_dir()
    profile_exists = profile_dir.exists() and any(profile_dir.iterdir())

    browser_login_age_hours: float | None = None
    marker = profile_dir / ".logged_in_at"
    if marker.exists():
        try:
            browser_login_age_hours = round((time.time() - float(marker.read_text())) / 3600, 2)
        except Exception:
            browser_login_age_hours = None

    token_meta = StockbitTokenStore(profile_dir / "token.json").inspect()

    return StockbitSessionStatus(
        profile_exists=profile_exists,
        profile_path=str(profile_dir),
        browser_login_age_hours=browser_login_age_hours,
        token_exists=token_meta.exists,
        token_state=token_meta.state,
        token_expires_at=token_meta.expires_at.isoformat() if token_meta.expires_at else None,
        token_seconds_remaining=token_meta.seconds_remaining,
        token_expiry_source=token_meta.expiry_source,
    )
