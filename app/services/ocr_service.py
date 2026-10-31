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
        """Enhance contrast, normalize lighting, and binarize for improved OCR accuracy."""
        if not CV2_AVAILABLE:
            from PIL import ImageOps
            img = Image.open(image_path)
            img = ImageOps.exif_transpose(img)
            return img.convert('L')

        # Robust read that supports paths with spaces or non-ASCII characters on Windows
        img = None
        try:
            with open(str(image_path), 'rb') as f:
                img_bytes = bytearray(f.read())
            img_arr = np.asarray(img_bytes, dtype=np.uint8)
            img = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
        except Exception:
            img = cv2.imread(str(image_path))

        if img is None:
            raise FileNotFoundError(f"Image could not be read from: {image_path}")

        # Check resolution: upscale small or low-res label images
        h, w = img.shape[:2]
        if max(h, w) < 1200:
            scale = max(1.5, min(3.0, 1600.0 / max(h, w, 1)))
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Contrast Limited Adaptive Histogram Equalization (CLAHE) for uneven lighting/shadows
        clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
        contrast = clahe.apply(gray)

        # Bilateral filter to smooth background noise while keeping sharp character edges
        denoised = cv2.bilateralFilter(contrast, d=7, sigmaColor=50, sigmaSpace=50)

        # Invert if text is light on dark background (mean luminance < 115)
        if np.mean(denoised) < 115:
            denoised = cv2.bitwise_not(denoised)

        # Adaptive thresholding for clean binarization
        binary = cv2.adaptiveThreshold(
            denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 15, 3
        )
        return binary

    @staticmethod
    def detect_sections(text):
        """Parse common food label sections such as Ingredients, Contains, May Contain, Nutrition, Warnings."""
        import re
        sections = {
            'ingredients': '',
            'contains': '',
            'may_contain': '',
            'allergens': '',
            'nutrition': '',
            'warnings': '',
            'is_cosmetic': False
        }
        if not text:
            return sections

        lower_text = text.lower()
        if any(term in lower_text for term in ['for external use only', 'apply to skin', 'shampoo', 'lotion', 'cosmetic', 'eau de parfum']):
            sections['is_cosmetic'] = True

        # Extract "May Contain"
        mc = re.search(r'(?:may\s+contain|traces\s+of)\s*[:\-]?\s*([^\n\.;]+)', text, flags=re.IGNORECASE)
        if mc:
            sections['may_contain'] = mc.group(1).strip()

        # Extract "Contains"
        c = re.search(r'(?<!may\s)contains?\s*[:\-]?\s*([^\n\.;]+)', text, flags=re.IGNORECASE)
        if c:
            sections['contains'] = c.group(1).strip()

        # Extract "Allergy Advice" / "Allergens"
        al = re.search(r'(?:allerg(?:y|ens?)\s*(?:advice|information)?)\s*[:\-]?\s*([^\n\.;]+)', text, flags=re.IGNORECASE)
        if al:
            sections['allergens'] = al.group(1).strip()

        # Extract Nutrition info snippet if present
        nut = re.search(r'(?:nutrition(?:al)?\s*(?:facts|information)?)\s*[:\-]?\s*([^\n\r]+(?:\n[^\n\r]+){1,4})', text, flags=re.IGNORECASE)
        if nut:
            sections['nutrition'] = nut.group(1).strip()

        # Extract Warnings
        warn = re.search(r'(?:warnings?|cautions?|caution)\s*[:\-]?\s*([^\n\.;]+)', text, flags=re.IGNORECASE)
        if warn:
            sections['warnings'] = warn.group(1).strip()

        return sections

    def extract_text(self, image_path):
        """Extract text from an ingredient label image with multi-pass OCR and fallback.

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
            extracted_text = ""
            if CV2_AVAILABLE:
                processed = self.preprocess_image(image_path)
                # Primary pass: standard OCR on preprocessed image
                extracted_text = pytesseract.image_to_string(processed, config='--oem 3 --psm 3')

                # If primary pass returned very little text, try secondary pass with psm 6 (uniform block)
                if len(extracted_text.strip()) < 15:
                    alt_text = pytesseract.image_to_string(processed, config='--oem 3 --psm 6')
                    if len(alt_text.strip()) > len(extracted_text.strip()):
                        extracted_text = alt_text
            else:
                from PIL import ImageOps
                img = Image.open(image_path)
                img = ImageOps.exif_transpose(img)
                extracted_text = pytesseract.image_to_string(img)

            cleaned_text = extracted_text.strip()
            # If no letters or less than 5 readable characters found
            import re
            letters_only = re.sub(r'[^a-zA-Z]', '', cleaned_text)
            if not cleaned_text or len(letters_only) < 3:
                return "No readable ingredient text could be detected from the image. Please ensure the label is well-lit, clearly in focus, and flat, or paste the ingredient text directly."
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
