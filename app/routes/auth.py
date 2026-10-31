import re
from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, session, current_app, make_response
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models.user import User, PasswordResetToken
from app.models.ingredient import Scan
from app.services.email_service import EmailService

auth_bp = Blueprint('auth', __name__)

EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$')


def _is_rate_limited(user: User) -> bool:
    """
    Checks if a user is submitting password reset requests too rapidly.
    Enforces a 60-second cooldown between requests and max 5 requests per hour.
    """
    now = datetime.now(timezone.utc)
    one_hour_ago = now - timedelta(hours=1)

    recent_tokens = PasswordResetToken.query.filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.created_at >= one_hour_ago
    ).order_by(PasswordResetToken.created_at.desc()).all()

    if recent_tokens:
        latest = recent_tokens[0]
        latest_created = latest.created_at
        if latest_created.tzinfo is None:
            latest_created = latest_created.replace(tzinfo=timezone.utc)

        # 60-second cooldown
        if (now - latest_created).total_seconds() < 60:
            return True

        # Max 5 requests per hour
        if len(recent_tokens) >= 5:
            return True

    return False


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """User authentication login route with pending scan preservation."""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    pending_scan_name = session.get('pending_scan_name')

    if request.method == 'POST':
        identifier = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not identifier or not password:
            flash('Please enter both username/email and password.', 'warning')
            return render_template('auth/login.html', pending_scan_name=pending_scan_name)

        # Lookup user by username or normalized email
        user = User.query.filter(
            (User.username == identifier) | (User.email == identifier.lower())
        ).first()

        if user and user.check_password(password):
            remember_choice = request.form.get('remember', '').lower() in ('true', '1', 'on', 'yes')
            login_user(user, remember=remember_choice)

            # Check if user had a scan pending authentication
            pending_scan_id = session.pop('pending_scan_id', None)
            session.pop('pending_scan_name', None)

            if pending_scan_id:
                scan = db.session.get(Scan, pending_scan_id)
                if scan:
                    if scan.user_id is None:
                        scan.user_id = user.id
                        db.session.commit()
                    flash(f'Welcome back, {user.username}! Your scan results for "{scan.product_name}" are ready below.', 'success')
                    return redirect(url_for('main.view_scan_results', scan_id=scan.id))

            flash(f'Welcome back, {user.username}!', 'success')
            next_page = request.args.get('next')
            # Security: ensure next_page starts with '/' to prevent open redirect vulnerabilities
            if next_page and next_page.startswith('/') and not next_page.startswith('//'):
                return redirect(next_page)
            return redirect(url_for('main.index'))
        else:
            flash('Invalid username/email or password.', 'danger')

    return render_template('auth/login.html', pending_scan_name=pending_scan_name)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """User registration route with field validation and pending scan preservation."""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    pending_scan_name = session.get('pending_scan_name')

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        # Validation
        if not username or not email or not password or not confirm_password:
            flash('All fields are required.', 'danger')
            return render_template('auth/register.html', pending_scan_name=pending_scan_name)

        if len(username) < 3:
            flash('Username must be at least 3 characters long.', 'warning')
            return render_template('auth/register.html', pending_scan_name=pending_scan_name)

        if not EMAIL_REGEX.match(email):
            flash('Please enter a valid email address.', 'warning')
            return render_template('auth/register.html', pending_scan_name=pending_scan_name)

        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'warning')
            return render_template('auth/register.html', pending_scan_name=pending_scan_name)

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/register.html', pending_scan_name=pending_scan_name)

        # Check existing account
        if User.query.filter_by(username=username).first():
            flash('Username is already taken. Please choose another.', 'warning')
            return render_template('auth/register.html', pending_scan_name=pending_scan_name)

        if User.query.filter_by(email=email).first():
            flash('An account with this email already exists. Please log in.', 'warning')
            return render_template('auth/register.html', pending_scan_name=pending_scan_name)

        # Create new user
        new_user = User(username=username, email=email)
        new_user.set_password(password)

        try:
            db.session.add(new_user)
            db.session.commit()

            # Automatically log the new user in for seamless UX
            login_user(new_user, remember=False)

            # Check if user had a scan pending authentication
            pending_scan_id = session.pop('pending_scan_id', None)
            session.pop('pending_scan_name', None)

            if pending_scan_id:
                scan = db.session.get(Scan, pending_scan_id)
                if scan:
                    if scan.user_id is None:
                        scan.user_id = new_user.id
                        db.session.commit()
                    flash(f'Account created successfully! Your scan results for "{scan.product_name}" are ready below.', 'success')
                    return redirect(url_for('main.view_scan_results', scan_id=scan.id))

            flash('Registration successful! Welcome to IngredientIQ.', 'success')
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/') and not next_page.startswith('//'):
                return redirect(next_page)
            return redirect(url_for('main.index'))

        except Exception:
            db.session.rollback()
            flash('An error occurred during registration. Please try again.', 'danger')

    return render_template('auth/register.html', pending_scan_name=pending_scan_name)


@auth_bp.route('/logout')
def logout():
    """
    Terminates user authentication securely and comprehensively:
    1. Removes user identity from current session via Flask-Login's logout_user().
    2. Clears all user session data while preserving Flask-Login's _remember invalidation flag.
    3. Explicitly deletes remember-me cookies on the response across standard paths/domains.
    4. Sets strict Cache-Control headers to defeat browser bfcache back-navigation.
    5. Flashes confirmation message and redirects to the public Home page with a full-page refresh.
    """
    if current_user.is_authenticated:
        logout_user()

    # Clear user session data while preserving remember cookie invalidation
    remember_val = session.get('_remember')
    session.clear()
    if remember_val:
        session['_remember'] = remember_val

    flash('You have been logged out successfully.', 'info')

    response = make_response(redirect(url_for('main.index')))

    # Explicitly expire and delete remember-me cookies across standard and configured paths/domains
    config = current_app.config
    remember_cookie_name = config.get("REMEMBER_COOKIE_NAME", "remember_token")
    domain = config.get("REMEMBER_COOKIE_DOMAIN")
    path = config.get("REMEMBER_COOKIE_PATH", "/")

    response.delete_cookie(remember_cookie_name, domain=domain, path=path)
    response.delete_cookie(remember_cookie_name, path='/')
    response.delete_cookie('remember_token', path='/')

    # Security: enforce strict cache invalidation on the logout redirect
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, private'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'

    return response


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """
    Forgot Password request handler.
    Validates email format, checks if email is registered in the database,
    enforces rate limiting, creates a secure token, and dispatches reset link via Gmail SMTP.
    """
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        email_raw = request.form.get('email', '')
        email = email_raw.strip().lower()

        if not email:
            flash('Please enter your email address.', 'warning')
            return render_template('auth/forgot_password.html')

        if not EMAIL_REGEX.match(email):
            flash('Please enter a valid email address.', 'warning')
            return render_template('auth/forgot_password.html', email=email_raw)

        # Session rate limit check to prevent rapid enumeration
        now_ts = datetime.now(timezone.utc).timestamp()
        session_attempts = session.get('failed_reset_attempts', [])
        session_attempts = [ts for ts in session_attempts if (now_ts - ts) < 600]
        if len(session_attempts) >= 10:
            flash('Too many requests. Please wait a few minutes before trying again.', 'warning')
            return render_template('auth/forgot_password.html', email=email_raw)

        # Search existing users table in configured application database
        user = User.query.filter_by(email=email).first()

        if not user:
            session_attempts.append(now_ts)
            session['failed_reset_attempts'] = session_attempts
            flash(
                'This email address is not registered with IngredientIQ. Please check your email or create a new account.',
                'warning'
            )
            return render_template('auth/forgot_password.html', email=email_raw)

        # Check rate limiting for registered user
        if _is_rate_limited(user):
            flash('Too many password reset requests. Please wait a moment before trying again.', 'warning')
            return render_template('auth/forgot_password.html', email=email_raw)

        # Generate secure reset token
        token_record, raw_token = PasswordResetToken.create_for_user(user, expires_in_minutes=30)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("We couldn't send the reset email right now. Please try again later.", 'danger')
            return render_template('auth/forgot_password.html', email=email_raw)

        # Construct reset URL using configured APP_BASE_URL (never untrusted Host headers)
        base_url = current_app.config.get('APP_BASE_URL', 'https://ingredientiq-cymt.onrender.com').rstrip('/')
        reset_url = f"{base_url}/auth/reset-password/{raw_token}"

        # Dispatch email via Gmail SMTP
        sent = EmailService.send_password_reset_email(
            to_email=user.email,
            username=user.username,
            reset_url=reset_url
        )

        if sent:
            flash('Password reset link sent successfully! Please check your email inbox.', 'success')
            return render_template('auth/forgot_password.html', email_sent=True)
        else:
            flash("We couldn't send the reset email right now. Please try again later.", 'danger')
            return render_template('auth/forgot_password.html', email=email_raw)

    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """
    Dedicated password reset page.
    Validates token from database, verifies unexpired and unused status,
    checks password strength, updates password hash, and marks token consumed.
    """
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    # Verify token validity against database
    token_record, user = PasswordResetToken.verify_token(token)

    if not token_record or not user:
        flash('This password reset link is invalid or has expired. Please request a new one.', 'danger')
        return render_template('auth/reset_password.html', token_invalid=True, token=token)

    if request.method == 'POST':
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        if not password or not confirm_password:
            flash('Both password fields are required.', 'danger')
            return render_template('auth/reset_password.html', token=token)

        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'warning')
            return render_template('auth/reset_password.html', token=token)

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/reset_password.html', token=token)

        try:
            # Update password hash in database using existing hashing standard
            user.set_password(password)
            # Invalidate the consumed token immediately
            token_record.mark_used()
            db.session.commit()

            # Invalidate any active session for security
            session.clear()

            flash('Your password has been successfully reset! You can now log in with your new password.', 'success')
            return redirect(url_for('auth.login'))
        except Exception:
            db.session.rollback()
            flash('An unexpected error occurred while resetting your password. Please try again.', 'danger')
            return render_template('auth/reset_password.html', token=token)

    return render_template('auth/reset_password.html', token=token)
