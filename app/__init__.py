import os
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import config_by_name

# Extensions instantiated globally for application factory pattern
db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to continue.'
login_manager.login_message_category = 'warning'


def create_app(config_name=None):
    """Application factory for IngredientIQ."""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    app = Flask(__name__)
    config_obj = config_by_name.get(config_name, config_by_name['default'])
    app.config.from_object(config_obj)

    # Allow runtime environment variable overrides (12-factor app)
    if os.environ.get('SECRET_KEY'):
        app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')

    if config_name == 'production' and not app.config.get('SECRET_KEY'):
        import warnings
        warnings.warn("CRITICAL: SECRET_KEY is not set for production. Please set SECRET_KEY in your environment.")

    # Ensure required runtime folders exist
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Initialize extensions with current app instance
    db.init_app(app)
    login_manager.init_app(app)

    # Register Blueprints
    from app.routes.main import main_bp
    from app.routes.auth import auth_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')

    # Configure user loader for Flask-Login
    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return User.query.get(int(user_id))
        except Exception:
            return None

    # Global context processor for common template variables
    @app.context_processor
    def inject_global_data():
        from datetime import datetime, timezone
        return {
            'app_name': 'IngredientIQ',
            'app_version': '1.0.0',
            'current_year': datetime.now(timezone.utc).year
        }

    # Enforce strict Cache-Control headers on sensitive and authenticated requests
    @app.after_request
    def set_cache_and_security_headers(response):
        """
        Enforce strict Cache-Control headers on sensitive, authenticated, and user-specific pages.
        Ensures browser Back button and history navigation cannot reveal private account info or cached pages.
        """
        from flask import request
        from flask_login import current_user
        sensitive_prefixes = ('/history', '/scan', '/admin', '/dashboard', '/account', '/profile', '/auth', '/export-report', '/uploads')
        if current_user.is_authenticated or any(request.path.startswith(prefix) for prefix in sensitive_prefixes):
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, private'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response

    # Custom HTTP error handlers
    @app.errorhandler(403)
    def forbidden_error(error):
        from flask import render_template
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def not_found_error(error):
        from flask import render_template
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        from flask import render_template
        import logging
        logging.error(f"Internal Server Error (500): {error}")
        db.session.rollback()
        return render_template('errors/500.html'), 500

    return app
