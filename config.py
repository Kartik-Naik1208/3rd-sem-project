import os
from pathlib import Path

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent

# Ensure the instance directory exists so SQLAlchemy can create/open the DB file
_instance_dir = BASE_DIR / 'instance'
_instance_dir.mkdir(parents=True, exist_ok=True)


def _load_env_file(env_path):
    """Lightweight built-in .env parser so environment variables are loaded without hard dependencies."""
    if not os.path.isfile(env_path):
        return
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, val = line.split('=', 1)
                key = key.strip()
                val = val.strip().strip('\'"')
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception:
        pass


# Try python-dotenv if installed, otherwise use our built-in fallback
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / '.env')
except ImportError:
    _load_env_file(BASE_DIR / '.env')

# Resolve database URL from environment or fallback to instance SQLite
_raw_db_url = os.environ.get('DATABASE_URL')
if _raw_db_url:
    # Render and other providers often specify postgres:// which SQLAlchemy 1.4+ expects as postgresql://
    if _raw_db_url.startswith('postgres://'):
        _raw_db_url = _raw_db_url.replace('postgres://', 'postgresql://', 1)
    _db_uri = _raw_db_url
    if 'sqlite' in _raw_db_url:
        _engine_options = {'connect_args': {'check_same_thread': False}}
    else:
        _engine_options = {}
else:
    _db_uri = 'sqlite:///' + (_instance_dir / 'ingredientiq.db').as_posix()
    _engine_options = {'connect_args': {'check_same_thread': False}}


class Config:
    """Base configuration with shared application settings."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'ingredientiq-dev-secret-key-2026')
    
    # Database configuration
    SQLALCHEMY_DATABASE_URI = _db_uri
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = _engine_options
    
    # Session & Cookie Security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.environ.get('FLASK_ENV') == 'production'
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_SECURE = os.environ.get('FLASK_ENV') == 'production'
    
    # Upload configurations
    UPLOAD_FOLDER = os.environ.get(
        'UPLOAD_FOLDER',
        str(BASE_DIR / 'app' / 'static' / 'uploads')
    )
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload size
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'bmp', 'tiff'}
    
    # Optional external OCR engine configuration
    TESSERACT_CMD = os.environ.get('TESSERACT_CMD', '')

    # Email / SMTP configuration (Gmail SMTP)
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ('true', '1', 'yes')
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'false').lower() in ('true', '1', 'yes')
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', os.environ.get('MAIL_USERNAME', 'noreply@ingredientiq.com'))

    # Base application URL for generating password reset links (prevents Host header manipulation)
    APP_BASE_URL = os.environ.get('APP_BASE_URL', 'https://ingredientiq-cymt.onrender.com').rstrip('/')


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    TESTING = False


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    APP_BASE_URL = 'http://localhost:5000'


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    TESTING = False
    # In production, SECRET_KEY must be provided via environment variable
    SECRET_KEY = os.environ.get('SECRET_KEY', None)


config_by_name = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
