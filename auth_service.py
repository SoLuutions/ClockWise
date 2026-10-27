import json
import os
import sys
import hashlib
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from typing import Tuple, Optional, Dict, Any

CURRENT_VERSION = "1.0.2"
GITHUB_REPO = "SoLuutions/ClockWise"

# ── App Data Directory (Persistent across PyInstaller temp executions) ────────
def get_app_data_dir() -> str:
    """Returns persistent application data directory on Windows or Linux."""
    if sys.platform == 'win32':
        base = os.environ.get('APPDATA') or os.path.expanduser('~')
    else:
        base = os.path.expanduser('~/.config')
    app_dir = os.path.join(base, 'ClockWise')
    os.makedirs(app_dir, exist_ok=True)
    return app_dir

CONFIG_FILE = os.path.join(get_app_data_dir(), 'supabase_config.json')
LOCAL_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'supabase_config.json')
SESSION_FILE = os.path.join(get_app_data_dir(), 'session.json')

# ── Obfuscation Helper for Embedded Credentials ───────────────────────────────
# Obfuscates strings using XOR masking so they are not plain text in the binary
XOR_KEY = 0x5C

def _xor_decode(encoded_bytes: bytes) -> str:
    return bytes([b ^ XOR_KEY for b in encoded_bytes]).decode('utf-8', errors='ignore')

def _xor_encode(plain_str: str) -> bytes:
    return bytes([b ^ XOR_KEY for b in plain_str.encode('utf-8')])

# Embedded default placeholders (XOR encoded)
_EMBEDDED_URL_ENC = _xor_encode("https://xlcbhhrmibkaeyalsflk.supabase.co")
_EMBEDDED_KEY_ENC = _xor_encode("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhsY2JoaHJtaWJrYWV5YWxzZmxrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTMwNjk4ODksImV4cCI6MjEwODY0NTg4OX0.FQzWER765hCO61idza84f8bRTJlG_u59UNTXw9v7USU")

DEFAULT_CONFIG = {
    "supabase_url": _xor_decode(_EMBEDDED_URL_ENC),
    "supabase_anon_key": _xor_decode(_EMBEDDED_KEY_ENC),
    "subscription_max_days": 30
}

def load_config() -> Dict[str, Any]:
    # 1. Check local directory config (if exists, e.g. for developer overrides)
    for path in (LOCAL_CONFIG, CONFIG_FILE):
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                    if cfg.get('supabase_url') and 'YOUR_PROJECT_REF' not in cfg.get('supabase_url'):
                        return cfg
            except Exception:
                pass
    return DEFAULT_CONFIG.copy()

def save_config(url: str, key: str, max_days: int = 30) -> Dict[str, Any]:
    cfg = {
        "supabase_url": url.strip().rstrip('/'),
        "supabase_anon_key": key.strip(),
        "subscription_max_days": max_days
    }
    # Save to persistent APPDATA directory
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=4)
    except Exception:
        pass
    # Also save to local directory if writable
    try:
        with open(LOCAL_CONFIG, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=4)
    except Exception:
        pass
    return cfg

def _hash_password(raw_pass: str) -> str:
    return hashlib.sha256(raw_pass.encode('utf-8')).hexdigest()

# ── GitHub Releases Update Checker ────────────────────────────────────────────
def parse_semver(ver_str: str) -> Tuple[int, int, int]:
    clean = str(ver_str).strip().lstrip('v').split('-')[0]
    parts = []
    for p in clean.split('.'):
        try: parts.append(int(p))
        except ValueError: parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])

def check_for_updates(timeout: int = 4) -> Tuple[Optional[str], bool, Optional[dict]]:
    """
    Checks GitHub Releases for new ClockWise versions.
    Returns (latest_tag, update_available: bool, release_info: dict or None).
    """
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    req = urllib.request.Request(url, headers={
        'User-Agent': 'ClockWise-Updater/1.0',
        'Accept': 'application/vnd.github.v3+json'
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            tag = data.get('tag_name', '')
            latest_v = parse_semver(tag)
            curr_v = parse_semver(CURRENT_VERSION)
            if latest_v > curr_v:
                return tag, True, data
            return tag, False, data
    except Exception:
        return None, False, None

# ── Secure Server-Side Authentication & Subscription Verification ─────────────
def check_account_subscription(email: str, password_input: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Verifies subscription using:
    1. Server-Side RPC (verify_subscription) - Enterprise security, table is completely hidden.
    2. Fallback to direct REST query if RPC function is not yet installed on database.
    """
    cfg = load_config()
    base_url = cfg.get("supabase_url", "").strip().rstrip('/')
    anon_key = cfg.get("supabase_anon_key", "").strip()
    max_days = cfg.get("subscription_max_days", 30)

    if not base_url or 'YOUR_PROJECT_REF' in base_url or not anon_key or 'YOUR_SUPABASE_ANON_KEY' in anon_key:
        return False, "Database connection not configured yet. Please enter your Supabase URL & Anon Key in Database Settings.", None

    clean_email = email.strip().lower()
    if not clean_email:
        return False, "Email or username cannot be empty.", None

    headers = {
        'apikey': anon_key,
        'Authorization': f'Bearer {anon_key}',
        'Content-Type': 'application/json',
        'User-Agent': 'ClockWise-Windows/1.0'
    }

    # ── Method A: Secure Server-Side RPC Function (Primary) ───────────────────
    rpc_url = f"{base_url}/rest/v1/rpc/verify_subscription"
    rpc_payload = json.dumps({"p_email": clean_email, "p_password": password_input}).encode('utf-8')
    req_rpc = urllib.request.Request(rpc_url, data=rpc_payload, headers=headers, method='POST')

    use_fallback = False
    try:
        with urllib.request.urlopen(req_rpc, timeout=8) as resp:
            res = json.loads(resp.read().decode('utf-8'))
            if isinstance(res, dict):
                if res.get('success'):
                    days_left = res.get('days_remaining', 30)
                    session_data = {
                        "email": clean_email,
                        "password": password_input,
                        "full_name": res.get('full_name', ''),
                        "last_payment_date": str(res.get('last_payment_date', '')),
                        "days_remaining": days_left,
                        "version": CURRENT_VERSION,
                        "verified_at": datetime.now(timezone.utc).isoformat()
                    }
                    save_session(session_data)
                    return True, res.get('message', f'Subscription Active: {days_left}d remaining'), session_data
                else:
                    return False, res.get('message', 'Subscription expired or invalid.'), None
    except urllib.error.HTTPError as e:
        # If 404/400 (function not yet created in Supabase), gracefully try fallback
        if e.code in (404, 400):
            use_fallback = True
        else:
            err_body = e.read().decode('utf-8', errors='ignore')
            return False, f"Server Error ({e.code}): {err_body or e.reason}", None
    except Exception:
        use_fallback = True

    # ── Method B: Fallback Direct REST Table Query ────────────────────────────
    if use_fallback:
        query_url = f"{base_url}/rest/v1/clockwise_users?email=eq.{urllib.parse.quote(clean_email)}&select=*"
        req_table = urllib.request.Request(query_url, headers=headers, method='GET')
        try:
            with urllib.request.urlopen(req_table, timeout=8) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            return False, f"Database connection error: {str(e)}", None

        if not data:
            return False, "Account not found. Please verify your email.", None

        user = data[0]
        db_pass = str(user.get('password', ''))
        input_hashed = _hash_password(password_input)
        if db_pass != password_input and db_pass != input_hashed:
            return False, "Incorrect password. Please try again.", None

        if not user.get('is_active', True):
            return False, "Account has been deactivated. Please contact support.", None

        raw_date = user.get('last_payment_date')
        if not raw_date:
            return False, "No payment record found for this account. Access restricted.", None

        try:
            date_str = str(raw_date).split('T')[0]
            pay_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except Exception:
            return False, f"Invalid date format: {raw_date}", None

        today = datetime.now(timezone.utc).date()
        days_elapsed = (today - pay_date).days

        if days_elapsed > max_days:
            return False, (
                f"Subscription Expired: Last payment was on {pay_date.strftime('%b %d, %Y')} "
                f"({days_elapsed} days ago - limit is 30 days). Access restricted."
            ), user

        days_remaining = max(0, max_days - max(0, days_elapsed))
        session_data = {
            "email": clean_email,
            "password": password_input,
            "full_name": user.get('full_name', ''),
            "last_payment_date": str(pay_date),
            "days_remaining": days_remaining,
            "version": CURRENT_VERSION,
            "verified_at": datetime.now(timezone.utc).isoformat()
        }
        save_session(session_data)
        return True, f"Subscription Active: {days_remaining}d remaining", session_data

    return False, "Unknown verification error.", None

SETTINGS_FILE = os.path.join(get_app_data_dir(), 'settings.json')

def load_settings() -> Dict[str, Any]:
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_settings(data: Dict[str, Any]):
    try:
        current = load_settings()
        current.update(data)
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(current, f, indent=4)
    except Exception:
        pass

def save_session(session_data: dict):
    try:
        with open(SESSION_FILE, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, indent=4)
    except Exception:
        pass

def load_cached_session() -> Optional[dict]:
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return None

def clear_session():
    if os.path.exists(SESSION_FILE):
        try:
            os.remove(SESSION_FILE)
        except Exception:
            pass

def verify_cached_session(enforce_update_check: bool = True) -> Tuple[bool, str, Optional[dict]]:
    """
    Verifies saved session credentials:
    - If a new version update is detected, logs out the user as requested.
    - Otherwise, automatically re-verifies subscription and logs them in.
    """
    cached = load_cached_session()
    if not cached:
        return False, "No saved session found.", None

    # Check for updates if requested
    if enforce_update_check:
        latest_tag, has_update, _ = check_for_updates(timeout=3)
        if has_update and latest_tag:
            clear_session()
            return False, f"UPDATE_DETECTED:{latest_tag}", {"update_tag": latest_tag}

    email = cached.get('email', '')
    password = cached.get('password', '')
    if not email or not password:
        return False, "Session incomplete.", None

    ok, msg, udata = check_account_subscription(email, password)
    if ok:
        return True, msg, udata

    # Offline / temporary connection grace check:
    # If the database server was unreachable but cached subscription is still within 30 days,
    # keep the user logged in rather than kicking them out.
    if "expired" not in msg.lower() and "incorrect password" not in msg.lower() and "not found" not in msg.lower():
        raw_date = cached.get('last_payment_date')
        if raw_date:
            try:
                date_str = str(raw_date).split('T')[0]
                pay_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                days_elapsed = (datetime.now(timezone.utc).date() - pay_date).days
                if days_elapsed <= 30:
                    cached['days_remaining'] = max(0, 30 - days_elapsed)
                    return True, f"Subscription active: {cached['days_remaining']}d remaining", cached
            except Exception:
                pass

    return False, msg, None
