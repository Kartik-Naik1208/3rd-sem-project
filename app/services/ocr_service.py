import os
import sys
import shutil
from pathlib import Path
from PIL import Image

# Graceful imports for OCR & image processing libraries
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    np = None

try:
    import pytesseract
    PYTESSERACT_AVAILABLE = True
except ImportError:
    PYTESSERACT_AVAILABLE = False


class TesseractNotFoundError(Exception):
    """Raised when the Tesseract OCR executable cannot be found on the system."""
    pass


class TesseractConfigError(TesseractNotFoundError):
    """Raised when TESSERACT_CMD is explicitly configured with an invalid or inaccessible path."""
    pass


def find_tesseract_cmd(cmd=None):
    """Locate and validate the Tesseract OCR executable.

    Priority:
    1. Explicit cmd parameter or TESSERACT_CMD environment variable.
       If set, it is validated. If the path does not exist, raises TesseractConfigError.
    2. System PATH via shutil.which('tesseract') or shutil.which('tesseract.exe').
    3. Common standard Windows installation directories (if on Windows and the file exists).

    Raises:
        TesseractConfigError: If an explicit/environment path is configured but invalid.
        TesseractNotFoundError: If Tesseract cannot be found in any of the above locations.
    """
    configured = cmd if cmd is not None else os.environ.get('TESSERACT_CMD', '')
    if configured and isinstance(configured, str):
        cleaned_cmd = configured.strip().strip('\'"')
        if cleaned_cmd:
            norm_path = os.path.normpath(cleaned_cmd)
            if os.path.isfile(norm_path):
                return norm_path
            raise TesseractConfigError(
                f"The configured Tesseract OCR path could not be found: '{cleaned_cmd}'. "
                "Please verify that the path points to a valid tesseract.exe executable, "
                "or remove TESSERACT_CMD to let the system detect it automatically."
            )

    # 2. Check system PATH
    path_match = shutil.which('tesseract') or shutil.which('tesseract.exe')
    if path_match:
        return os.path.normpath(path_match)

    # 3. Check common standard Windows installation paths
    if os.name == 'nt' or sys.platform.startswith('win'):
        common_candidates = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe"),
        ]
        for candidate in common_candidates:
            if candidate and os.path.isfile(candidate):
                return os.path.normpath(candidate)

    # 4. Tesseract not found anywhere
    raise TesseractNotFoundError(
        "Tesseract OCR is not installed or could not be located. "
        "Install Tesseract OCR for Windows, then configure TESSERACT_CMD with the "
        "full path to tesseract.exe or add its installation directory to your system PATH. "
        "Restart the application and try again."
    )


def _check_tesseract(cmd=None):
    """Verify the Tesseract binary is accessible and executable.

    Configures pytesseract.pytesseract.tesseract_cmd and verifies execution.
    Raises TesseractNotFoundError or TesseractConfigError if inaccessible.
    """
    if not PYTESSERACT_AVAILABLE:
        raise TesseractNotFoundError(
            "The pytesseract Python package is not installed. "
            "Install it with: pip install pytesseract"
        )

    resolved_path = find_tesseract_cmd(cmd)
    pytesseract.pytesseract.tesseract_cmd = resolved_path

    try:
        pytesseract.get_tesseract_version()
        return resolved_path
    except (pytesseract.pytesseract.TesseractNotFoundError, FileNotFoundError):
        raise TesseractNotFoundError(
            "Tesseract OCR is not installed or could not be located. "
            "Install Tesseract OCR for Windows, then configure TESSERACT_CMD with the "
            "full path to tesseract.exe or add its installation directory to your system PATH. "
            "Restart the application and try again."
        )
    except Exception as exc:
        raise TesseractNotFoundError(
            f"Could not initialize Tesseract OCR from '{resolved_path}': {exc}"
        )


class OCRService:
    """Process label images and extract text using OpenCV pre-processing and Tesseract OCR."""

    def __init__(self, tesseract_cmd=None):
        self.tesseract_cmd = tesseract_cmd

    @staticmethod
    def is_tesseract_available(cmd=None):
        """Return True if Tesseract is installed and accessible, False otherwise."""
        try:
            _check_tesseract(cmd)
            return True
        except (TesseractNotFoundError, TesseractConfigError):
            return False

    @staticmethod
    def get_tesseract_path(cmd=None):
        """Return the resolved tesseract executable path, or None if unavailable."""
        try:
            return find_tesseract_cmd(cmd)
        except (TesseractNotFoundError, TesseractConfigError):
            return None

    def preprocess_image(self, image_path):
        """Enhance contrast and convert to grayscale for improved OCR accuracy."""
        if not CV2_AVAILABLE:
            return Image.open(image_path).convert('L')

        img = cv2.imread(str(image_path))
        if img is None:
            raise FileNotFoundError(f"Image could not be read from: {image_path}")

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        processed = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2,
        )
        return processed

    def extract_text(self, image_path):
        """Extract text from an ingredient label image.

        Raises:
            TesseractNotFoundError: when the Tesseract binary is missing.
            TesseractConfigError: when the configured Tesseract binary path is invalid.
            FileNotFoundError: when the image file cannot be read.
            RuntimeError: when OCR extraction fails unexpectedly.
        """
        if not PYTESSERACT_AVAILABLE:
            raise TesseractNotFoundError(
                "pytesseract is not installed. Install it with: pip install pytesseract"
            )

        # Verify and configure tesseract before processing
        _check_tesseract(self.tesseract_cmd)

        try:
            if CV2_AVAILABLE:
                processed = self.preprocess_image(image_path)
                text = pytesseract.image_to_string(processed)
            else:
                img = Image.open(image_path)
                text = pytesseract.image_to_string(img)

            cleaned_text = text.strip()
            if not cleaned_text:
                return "No text could be detected from the image. Please try a clearer picture."
            return cleaned_text

        except (TesseractNotFoundError, TesseractConfigError):
            raise
        except pytesseract.pytesseract.TesseractNotFoundError:
            raise TesseractNotFoundError(
                "Tesseract OCR is not installed or could not be located. "
                "Install Tesseract OCR for Windows, then configure TESSERACT_CMD with the "
                "full path to tesseract.exe or add its installation directory to your system PATH. "
                "Restart the application and try again."
            )
        except Exception as exc:
            raise RuntimeError(
                f"OCR processing failed: {exc}. "
                "Try using a higher-quality image or paste the ingredient text directly."
            )
