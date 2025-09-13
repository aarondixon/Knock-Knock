"""
Flask application for managing an IP allow list via a self-service web portal.

Features:
- User-facing interface to request IP access with expiration options
- Admin panel for viewing, filtering, and managing IP entries
- Background job to clean up expired IPs
- Integration with router APIs (e.g., Unifi)
- Rate-limited admin login
"""

# -------------------------------
# Imports
# -------------------------------
import os
from flask import Flask, request, render_template, redirect, flash, session, g, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager, login_required, login_user, current_user, logout_user
from flask_talisman import Talisman
from apscheduler.schedulers.background import BackgroundScheduler
import logging
import jwt
import sqlite3
import requests
import ipaddress
import re
from requests.models import Response
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import router_factory
from forms import AdminUser, KnockForm, AdminLoginForm, RevokeForm, ExtendForm

# -------------------------------
# Configuration & Initialization
# -------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY')
if not app.secret_key:
    raise RuntimeError("SECRET_KEY environment variable not set!") #Ensure app won't run without secret key
    
app.config['SESSION_COOKIE_SECURE'] = True  # Only send cookies over HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevent JavaScript access
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Mitigate CSRF

csp = {
    'default-src': [
        '\'self\'',  # Only allow content from your own domain
    ],
    'script-src': [
        '\'self\'',
        'https://cdn.jsdelivr.net',
        'https://cdn.datatables.net',
        'https://code.jquery.com',
    ],
    'style-src': [
        '\'self\'',
        'https://cdn.jsdelivr.net',
        'https://cdn.datatables.net',
    ],
    'font-src': [
        '\'self\'',
        'https://cdn.jsdelivr.net',
        'https://cdn.datatables.net',
    ],
    'img-src': [
        '\'self\'',
        'data:',  # Allow inline images if needed
    ],
    'connect-src': [
        '\'self\'',
    ]
}

Talisman(app, force_https=False, content_security_policy=csp)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'index'

csrf = CSRFProtect(app)

limiter = Limiter(get_remote_address, app=app)

db_path = '/data/db.sqlite'
TITLE = os.environ.get('TITLE','Knock-Knock')

router = router_factory.get_router(os.environ.get("ROUTER_TYPE", "unifi"))

logging.basicConfig(level=logging.INFO,format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

@login_manager.user_loader
def load_user(user_id):
    return AdminUser(user_id) if user_id == 'admin' else None

def parse_expiration_options(raw):
    options = raw.split(',')

    labels = {
        'h': 'Hour',
        'd': 'Day',
        'w': 'Week',
        'm': 'Month',
        'y': 'Year',
        'f': 'Forever'
    }

    choices = []
    for opt in options:
        if opt == '0f':
            choices.append((opt, 'Forever'))
            continue

        match = re.match(r"(\d+)([hdwmyf])", opt)
        if match:
            num, unit = match.groups()
            label = f"{num} {labels.get(unit, unit)}{'s' if int(num) > 1 else ''}"
            choices.append((opt, label))
    return choices

EXPIRATION_OPTIONS = parse_expiration_options(os.environ.get('EXPIRATION_OPTIONS','1h,1d,1w,1m'))
logger.info("EXPIRATION OPTIONS = %s", EXPIRATION_OPTIONS)

# -------------------------------
# Utility Functions
# -------------------------------
def get_expiration_delta(duration: str) -> timedelta:
    """
    Returns a timedelta based on a duration string
    """
    mapping = {
        'h': lambda n: timedelta(hours=n),
        'd': lambda n: timedelta(days=n),
        'w': lambda n: timedelta(weeks=n),
        'm': lambda n: timedelta(days=30 * n),
        'y': lambda n: timedelta(days=365 * n),
    }

    if duration == '0f':
        return None #timedelta(days=365 * 10) # 10 years
    
    match = re.match(r"(\d+)([hdwmy])", duration)
    if match:
        num, unit = int(match.group(1)), match.group(2)
        return mapping.get(unit, lambda n: timedelta(days=1))(num)

    return timedelta(days=1)

# -------------------------------
# Database Functions
# -------------------------------

# --- Connection Helpers
def get_db():
    """
    Returns a SQLite connection stored in Flasks 'g' object for reuse during the request.
    """
    if 'db' not in g:
        g.db = sqlite3.connect(db_path)
    return g.db    

@app.teardown_appcontext
def close_db(exception):
    """
    Closes the database connection at the end of the request.
    """
    db = g.pop('db',None)
    if db is not None:
        db.close()

# --- Utility Functions
def init_db():
    """
    Intializes the database schema if it doesn't already exist.
    """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS access_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT,
                    ip TEXT,
                    expiration DATETIME
                )''')
    conn.commit()
    conn.close()

def get_user_ips(email):
    """
    Returns all IPs and expiration times assocated with a given email.
    """
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT ip, expiration FROM access_requests WHERE email = ?", (email,))
    return c.fetchall()

def get_all_entries(email_filter='', ip_filter='', sort='expiration'):
    """
    Returns all access entries. Filtering and sorting is done client-side.
    """
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT email, ip, expiration FROM access_requests")
    return c.fetchall()    

def cleanup_expired_ips():
    """
    Removes expired IPs from the database and calls the router to revoke access.
    """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT ip FROM access_requests WHERE expiration < ?", (datetime.now(),))
    expired_ips = c.fetchall()

    if expired_ips:
        router.ensure_authenticated()
        for (ip,) in expired_ips:
            try:
                router.remove_ip(ip)
                c.execute("DELETE FROM access_requests WHERE expiration < ?", (datetime.now(),))
            except Exception as e:
                print(f"Failed to remove IP {ip}: {e}")
        conn.commit()

    conn.close()

# -------------------------------
# Template Filters
# -------------------------------
@app.template_filter('localtime')
def localtime_filter(utc_dt):
    """
    Converts UTC datetime string or object to local time using the TZ environment variable. 
    Returns formatted string.
    """
    try:
        if isinstance(utc_dt, str):
            utc_dt = datetime.fromisoformat(utc_dt) # convert to timestamp if it's a string
        
        if utc_dt.tzinfo is None:
            utc_dt = utc_dt.replace(tzinfo=timezone.utc)

        user_tz_str = session.get('user_timezone', 'UTC')
        user_tz = ZoneInfo(user_tz_str)

        local_dt = utc_dt.astimezone(user_tz)
        
        return local_dt.strftime('%Y-%m-%d %H:%M:%S %Z')
    except Exception as e:
        return f"Invalid timestamp: {e}"

# -------------------------------
# Routes
# -------------------------------

# --- Utility routes

@app.route('/favicon.ico')
@csrf.exempt
def favicon():
    return app.send_static_file('favicon.ico')

@app.route('/set-timezone', methods=['POST'])
def set_timezone():
    data = request.get_json()
    timezone = data.get('timezone')
    if timezone:
        session['user_timezone'] = timezone
        return jsonify({'status': 'ok', 'timezone': timezone})
    return jsonify({'status': 'error', 'message': 'No timezone provided'}), 400

@limiter.limit("5 per minute")
@app.route('/admin-login', methods=['POST'])
def admin_login():
    """
    Called by 'Admin Login' button. Prompts for password, routes to admin page if valid.
    """ 
    form = AdminLoginForm()
    if form.validate_on_submit():
        password = form.admin_password.data
        expected = os.environ.get('ADMIN_PASSWORD')

        if password == expected:
            user = AdminUser('admin')
            login_user(user)
            flash("Logged in as admin.", "success")
            return redirect('/admin')
        else:
            flash("Invalid admin password.", "danger")
    return redirect('/')

@app.route('/admin-logout')
@login_required
def admin_logout():
    logout_user()
    flash("Logged out successfully.", "info")
    return redirect('/')

@app.route('/revoke', methods=['POST'])
def revoke():
    """
    Removes IP from database so it is removed from allow list next scheduled job cycle.
    """
    form = RevokeForm()
    if form.validate_on_submit():
        ip = form.ip.data
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM access_requests WHERE ip = ?", (ip,))
        conn.commit()
        flash(f"Access for IP {ip} has been revoked. It will be removed on the next scheduled job cycle.", "warning")
    else:
        flash("Error validating form", "danger")
    return redirect('/admin')

@app.route('/extend', methods=['POST'])
def extend():
    """
    Extends the expiration time for a given IP based on selected duration.
    """
    form = ExtendForm(expiration_choices=EXPIRATION_OPTIONS)
    if form.validate_on_submit():
        ip = form.ip.data
        #duration = request.form['duration']
        duration = form.duration.data
        delta = get_expiration_delta(duration)

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT expiration FROM access_requests WHERE ip = ?", (ip,))
        row = c.fetchone()

        new_exp = None
        if row:
            if delta is not None:
                current_exp = datetime.fromisoformat(row[0])
                new_exp = (current_exp + delta).isoformat()
            c.execute("UPDATE access_requests SET expiration = ? WHERE ip = ?", (new_exp, ip))
            conn.commit()
            flash(f"Access for IP {ip} extended by {duration}.", "success")
    else:
        flash("Error validating form", "danger")

    return redirect('/admin')

# --- Navigation

@app.route('/', methods=['GET', 'POST'])
def index():
    """
    Main user-facing route. Displays current IP and allows user to request access.
    Uses Cloudflare headers to get email and IP.
    """
    email = request.headers.get('Cf-Access-Authenticated-User-Email', 'test@example.com')
    ip = request.headers.get('Cf-Connecting-IP', request.remote_addr)
    is_ipv6 = ipaddress.ip_address(ip).version == 6

    form = KnockForm(expiration_choices=EXPIRATION_OPTIONS)
    admin_form = AdminLoginForm()

    if form.validate_on_submit():
        duration = form.duration.data
        delta = get_expiration_delta(duration)
        if delta is None:
            expiration = None
        else:
            expiration = datetime.now(timezone.utc) + delta

        response, was_added = router.add_ip(ip)

        if response and response.status_code == 200:
            if was_added:
                # store access request in database
                conn = get_db()
                c = conn.cursor()
                c.execute("INSERT INTO access_requests (email, ip, expiration) VALUES (?, ?, ?)",
                        (email, ip, expiration))
                conn.commit()
                flash("Your IP has been successfully added to the allow list.", "success")
            else:
                flash("Your IP is already in the allow list.", "info")
            return redirect('/')
        else:
            flash("Failed to add IP to allow list. Please try again or contact support.", "danger")

    user_ips = get_user_ips(email)
    return render_template('index.html', email=email, ip=ip, user_ips=user_ips, form=form, admin_form=admin_form, is_ipv6=is_ipv6, title=TITLE)

@app.route('/admin')
@login_required
def admin():
    """
    Admin panel. Redirects to main page if access hasn't been granted.
    """
    if current_user.id != 'admin':
        flash("Admin access required.", "danger")
        return redirect('/')
    
    entries = get_all_entries()
    return render_template('admin.html', entries=entries, revoke_form=RevokeForm(), extend_form=ExtendForm(expiration_choices=EXPIRATION_OPTIONS), title=TITLE)

# -------------------------------
# Scheduler Setup
# -------------------------------
scheduler = BackgroundScheduler()
scheduler.add_job(cleanup_expired_ips, 'interval', minutes=60)
scheduler.start()

# -------------------------------
# Main Entry Point
# -------------------------------

init_db()
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9009)