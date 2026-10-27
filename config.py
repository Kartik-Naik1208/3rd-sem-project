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

class Config:
    """Base configuration with shared application settings."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'ingredientiq-dev-secret-key-2026')
    
    # SQLite Database URI — uses an absolute, forward-slash path so it resolves
    # correctly regardless of the working directory the app is launched from.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'sqlite:///' + (_instance_dir / 'ingredientiq.db').as_posix()
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Allow SQLite connections from multiple threads (required by Flask dev server)
    SQLALCHEMY_ENGINE_OPTIONS = {'connect_args': {'check_same_thread': False}}
    
    # Upload configurations
    UPLOAD_FOLDER = os.environ.get(
        'UPLOAD_FOLDER',
        str(BASE_DIR / 'app' / 'static' / 'uploads')
    )
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload size
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'bmp', 'tiff'}
    
    # Optional external OCR engine configuration
    TESSERACT_CMD = os.environ.get('TESSERACT_CMD', '')


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
