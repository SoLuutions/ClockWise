import json
import os
import hashlib
import urllib.request
import urllib.parse
from datetime import datetime, date, timezone
from typing import Tuple, Optional, Dict, Any

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'supabase_config.json')
SESSION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'session.json')

DEFAULT_CONFIG = {
    "supabase_url": "https://YOUR_PROJECT_REF.supabase.co",
    "supabase_anon_key": "YOUR_SUPABASE_ANON_KEY",
    "subscription_max_days": 30
}

def load_config() -> Dict[str, Any]:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(url: str, key: str, max_days: int = 30):
    cfg = {
        "supabase_url": url.strip().rstrip('/'),
        "supabase_anon_key": key.strip(),
        "subscription_max_days": max_days
    }
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=4)
    return cfg

def _hash_password(raw_pass: str) -> str:
    return hashlib.sha256(raw_pass.encode('utf-8')).hexdigest()

def check_account_subscription(email: str, password_input: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Queries Supabase database table 'clockwise_users':
    1. Checks if the account exists.
    2. Verifies the password (supports plain text or sha256).
    3. Checks if is_active is True.
    4. Calculates days since last_payment_date.
       - If <= 30 days: Access Granted.
       - If > 30 days: Access Restricted (Subscription Expired).
    Returns (success: bool, message: str, user_data: dict or None).
    """
    cfg = load_config()
    base_url = cfg.get("supabase_url", "").strip().rstrip('/')
    anon_key = cfg.get("supabase_anon_key", "").strip()
    max_days = cfg.get("subscription_max_days", 30)

    if not base_url or 'YOUR_PROJECT_REF' in base_url or not anon_key or 'YOUR_SUPABASE_ANON_KEY' in anon_key:
        return False, "Supabase connection is not configured yet. Please enter your Supabase URL & Anon Key in the setup menu.", None

    clean_email = email.strip().lower()
    if not clean_email:
        return False, "Email or username cannot be empty.", None

    # Query Supabase via PostgREST REST API
    query_url = f"{base_url}/rest/v1/clockwise_users?email=eq.{urllib.parse.quote(clean_email)}&select=*"
    req = urllib.request.Request(query_url, method='GET')
    req.add_header('apikey', anon_key)
    req.add_header('Authorization', f'Bearer {anon_key}')
    req.add_header('Content-Type', 'application/json')
    req.add_header('User-Agent', 'ClockWise-Windows/1.0')

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode('utf-8', errors='ignore')
        return False, f"Server HTTP error ({e.code}): {err_msg or e.reason}", None
    except urllib.error.URLError as e:
        return False, f"Network error connecting to database: {e.reason}", None
    except Exception as e:
        return False, f"Unexpected error: {str(e)}", None

    if not data or len(data) == 0:
        return False, "Account not found. Please verify your email or sign up.", None

    user = data[0]

    # Verify password (matches plain text or sha256)
    db_pass = str(user.get('password', ''))
    input_hashed = _hash_password(password_input)
    if db_pass != password_input and db_pass != input_hashed:
        return False, "Incorrect password. Please try again.", None

    # Check active status
    if not user.get('is_active', True):
        return False, "Account has been deactivated. Please contact support.", None

    # Verify payment date (30-day limit)
    raw_date = user.get('last_payment_date')
    if not raw_date:
        return False, "No payment record found for this account. Access restricted.", None

    try:
        # Support 'YYYY-MM-DD' or 'YYYY-MM-DDTHH:MM:SS...'
        date_str = str(raw_date).split('T')[0]
        pay_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except Exception:
        return False, f"Invalid date format in database: {raw_date}", None

    today = datetime.now(timezone.utc).date()
    days_elapsed = (today - pay_date).days

    if days_elapsed > max_days:
        return False, (
            f"Subscription Expired: Last payment was on {pay_date.strftime('%b %d, %Y')} "
            f"({days_elapsed} days ago). Access is restricted until renewed."
        ), user

    days_remaining = max(0, max_days - max(0, days_elapsed))
    success_msg = f"Subscription Active: {days_remaining} day{'s' if days_remaining != 1 else ''} remaining."
    
    # Store session
    session_data = {
        "email": clean_email,
        "password": password_input,
        "full_name": user.get('full_name', ''),
        "last_payment_date": str(pay_date),
        "days_remaining": days_remaining,
        "verified_at": datetime.now(timezone.utc).isoformat()
    }
    save_session(session_data)

    return True, success_msg, session_data

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

def verify_cached_session() -> Tuple[bool, str, Optional[dict]]:
    cached = load_cached_session()
    if not cached:
        return False, "No active session found.", None
    email = cached.get('email', '')
    password = cached.get('password', '')
    if not email or not password:
        return False, "Session incomplete.", None
    return check_account_subscription(email, password)
