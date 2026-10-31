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
    3. Standard platform-specific installation directories:
       - On Windows: standard Program Files and LocalAppData paths.
       - On Linux / Render / Docker: /usr/bin, /usr/local/bin, .apt unpacked paths.

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

    # 3. Check common standard installation paths based on OS
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
    else:
        # Standard Linux / Docker / Render paths
        linux_candidates = [
            "/usr/bin/tesseract",
            "/usr/local/bin/tesseract",
            "/opt/homebrew/bin/tesseract",
            # Render native environment unpacked directory fallbacks:
            os.path.join(os.getcwd(), ".apt", "usr", "bin", "tesseract"),
            "/opt/render/project/src/.apt/usr/bin/tesseract",
            os.path.expanduser("~/.local/bin/tesseract"),
        ]
        for candidate in linux_candidates:
            if candidate and os.path.isfile(candidate):
                return candidate

    # 4. Tesseract not found anywhere - OS-tailored diagnostic guidance
    if os.name == 'nt' or sys.platform.startswith('win'):
        raise TesseractNotFoundError(
            "Tesseract OCR is not installed or could not be located. "
            "Install Tesseract OCR for Windows, then configure TESSERACT_CMD with the "
            "full path to tesseract.exe or add its installation directory to your system PATH. "
            "Restart the application and try again."
        )
    else:
        raise TesseractNotFoundError(
            "Tesseract OCR is not installed or could not be located on this Linux system. "
            "Ensure tesseract-ocr is installed in your Dockerfile (apt-get install -y tesseract-ocr tesseract-ocr-eng) "
            "or set TESSERACT_CMD to the tesseract binary location. On Render, deploy using Docker runtime."
        )


def configure_tessdata_prefix():
    """Ensure TESSDATA_PREFIX is configured if standard directories exist and are unconfigured."""
    if os.environ.get('TESSDATA_PREFIX') and os.path.isdir(os.environ['TESSDATA_PREFIX']):
        return os.environ['TESSDATA_PREFIX']

    candidates = [
        # Linux standard paths
        "/usr/share/tesseract-ocr/5/tessdata",
        "/usr/share/tesseract-ocr/4.00/tessdata",
        "/usr/share/tessdata",
        "/usr/local/share/tessdata",
        # Local / Render .apt unpacked paths
        os.path.join(os.getcwd(), ".apt", "usr", "share", "tesseract-ocr", "5", "tessdata"),
        os.path.join(os.getcwd(), ".apt", "usr", "share", "tesseract-ocr", "4.00", "tessdata"),
        os.path.join(os.getcwd(), ".apt", "usr", "share", "tessdata"),
        "/opt/render/project/src/.apt/usr/share/tesseract-ocr/5/tessdata",
        "/opt/render/project/src/.apt/usr/share/tessdata",
        # Windows standard path
        r"C:\Program Files\Tesseract-OCR\tessdata",
    ]
    for candidate in candidates:
        if candidate and os.path.isdir(candidate):
            if os.path.isfile(os.path.join(candidate, 'eng.traineddata')):
                os.environ['TESSDATA_PREFIX'] = candidate
                return candidate
    return None


def get_installed_languages(cmd=None):
    """Return a list of language codes installed and available to Tesseract."""
    if not PYTESSERACT_AVAILABLE:
        return []
    try:
        resolved_path = find_tesseract_cmd(cmd)
        pytesseract.pytesseract.tesseract_cmd = resolved_path
        configure_tessdata_prefix()
        langs = pytesseract.get_languages(config='')
        return [l.strip() for l in langs if l.strip()]
    except Exception:
        pass

    try:
        import subprocess
        resolved_path = find_tesseract_cmd(cmd)
        res = subprocess.run([resolved_path, '--list-langs'], capture_output=True, text=True, timeout=5)
        lines = res.stdout.strip().splitlines()
        langs = []
        for line in lines:
            line_str = line.strip()
            if line_str and not line_str.lower().startswith('list of'):
                langs.append(line_str)
        return langs
    except Exception:
        return []


def check_ocr_health(cmd=None, required_langs=None, optional_langs=None):
    """Perform a comprehensive diagnostic check on Tesseract OCR and pytesseract.

    Verifies:
      1. Tesseract executable exists and is executable.
      2. Tesseract version can be retrieved.
      3. English language data ('eng') is available.
      4. Any additional configured required languages are available.
      5. pytesseract can successfully invoke the Tesseract executable.
      6. Evaluates optional languages (e.g. 'hin', 'osd') without failing overall health.

    Returns a dictionary of health status metrics.
    """
    if required_langs is None:
        required_langs = ['eng']
    if optional_langs is None:
        optional_langs = ['hin', 'osd']

    result = {
        'status': 'error',
        'is_available': False,
        'executable_path': None,
        'version': None,
        'installed_languages': [],
        'missing_required_languages': [],
        'available_optional_languages': [],
        'missing_optional_languages': [],
        'pytesseract_functional': False,
        'message': '',
        'error': None
    }

    if not PYTESSERACT_AVAILABLE:
        result['message'] = 'pytesseract Python package is not installed. Install with: pip install pytesseract'
        result['error'] = 'pytesseract_not_installed'
        return result

    # 1. Locate executable
    try:
        executable = find_tesseract_cmd(cmd)
        result['executable_path'] = executable
    except Exception as e:
        result['message'] = str(e)
        result['error'] = 'executable_not_found'
        return result

    # Configure pytesseract
    pytesseract.pytesseract.tesseract_cmd = executable
    configure_tessdata_prefix()

    # 2. Retrieve version
    try:
        version_str = str(pytesseract.get_tesseract_version()).strip()
        result['version'] = version_str
    except Exception as e:
        result['message'] = f"Failed to retrieve Tesseract version via pytesseract: {e}"
        result['error'] = 'version_retrieval_failed'
        return result

    # 3. Retrieve available languages
    installed_langs = get_installed_languages(executable)
    result['installed_languages'] = installed_langs

    # Check required languages (default: 'eng')
    for req in required_langs:
        if req not in installed_langs:
            result['missing_required_languages'].append(req)

    # Check optional languages (e.g. 'hin', 'osd')
    for opt in optional_langs:
        if opt in installed_langs:
            result['available_optional_languages'].append(opt)
        else:
            result['missing_optional_languages'].append(opt)

    # 4. Perform functional micro-invocation
    try:
        test_img = Image.new('RGB', (20, 20), color=(255, 255, 255))
        pytesseract.image_to_string(test_img, config='--oem 3 --psm 3')
        result['pytesseract_functional'] = True
    except Exception as e:
        result['status'] = 'error'
        result['is_available'] = False
        result['message'] = f"Tesseract execution invocation test failed: {e}"
        result['error'] = 'invocation_failed'
        return result

    # Determine overall status
    if result['missing_required_languages']:
        result['status'] = 'degraded'
        result['is_available'] = False
        result['message'] = (
            f"Tesseract is installed (v{version_str}), but required language data is missing: "
            f"{', '.join(result['missing_required_languages'])}. Available: {', '.join(installed_langs) or 'none'}."
        )
    else:
        result['status'] = 'healthy'
        result['is_available'] = True
        notes = []
        if result['available_optional_languages']:
            notes.append(f"Optional active: {', '.join(result['available_optional_languages'])}")
        if result['missing_optional_languages']:
            notes.append(f"Optional uninstalled: {', '.join(result['missing_optional_languages'])}")
        opt_note = f" ({'; '.join(notes)})" if notes else ""
        result['message'] = (
            f"Tesseract OCR v{version_str} operational at '{executable}' with languages: "
            f"{', '.join(installed_langs)}{opt_note}."
        )

    return result


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
    configure_tessdata_prefix()

    try:
        pytesseract.get_tesseract_version()
        return resolved_path
    except (pytesseract.pytesseract.TesseractNotFoundError, FileNotFoundError):
        if os.name == 'nt' or sys.platform.startswith('win'):
            raise TesseractNotFoundError(
                "Tesseract OCR is not installed or could not be located. "
                "Install Tesseract OCR for Windows, then configure TESSERACT_CMD with the "
                "full path to tesseract.exe or add its installation directory to your system PATH. "
                "Restart the application and try again."
            )
        else:
            raise TesseractNotFoundError(
                "Tesseract OCR is not installed or could not be located on this Linux system. "
                "Ensure tesseract-ocr is installed in your Dockerfile (apt-get install -y tesseract-ocr tesseract-ocr-eng) "
                "or set TESSERACT_CMD to the tesseract binary location. On Render, deploy using Docker runtime."
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

    @staticmethod
    def check_health(cmd=None, required_langs=None, optional_langs=None):
        """Perform diagnostic OCR verification and return health report."""
        return check_ocr_health(cmd, required_langs, optional_langs)

    def extract_text(self, image_path, lang=None):
        """Extract text from an ingredient label image with multi-pass OCR and fallback.

        Args:
            image_path: Path to the image file.
            lang: Language string (e.g. 'eng', 'eng+hin'). Defaults to 'eng' or 'eng+hin'
                  if Hindi is enabled and installed.

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
        resolved_cmd = _check_tesseract(self.tesseract_cmd)

        # Determine OCR language
        ocr_lang = lang
        if not ocr_lang:
            available_langs = get_installed_languages(resolved_cmd)
            hindi_enabled = os.environ.get('ENABLE_HINDI_OCR', 'false').lower() in ('1', 'true', 'yes')
            if hindi_enabled and 'hin' in available_langs:
                ocr_lang = 'eng+hin'
            else:
                ocr_lang = 'eng'

        try:
            extracted_text = ""
            if CV2_AVAILABLE:
                processed = self.preprocess_image(image_path)
                # Primary pass: standard OCR on preprocessed image
                try:
                    extracted_text = pytesseract.image_to_string(processed, lang=ocr_lang, config='--oem 3 --psm 3')
                except Exception:
                    # Fallback to default eng if custom lang pack encounters runtime syntax issue
                    extracted_text = pytesseract.image_to_string(processed, lang='eng', config='--oem 3 --psm 3')

                # If primary pass returned very little text, try secondary pass with psm 6 (uniform block)
                if len(extracted_text.strip()) < 15:
                    try:
                        alt_text = pytesseract.image_to_string(processed, lang=ocr_lang, config='--oem 3 --psm 6')
                    except Exception:
                        alt_text = pytesseract.image_to_string(processed, lang='eng', config='--oem 3 --psm 6')
                    if len(alt_text.strip()) > len(extracted_text.strip()):
                        extracted_text = alt_text
            else:
                from PIL import ImageOps
                img = Image.open(image_path)
                img = ImageOps.exif_transpose(img)
                try:
                    extracted_text = pytesseract.image_to_string(img, lang=ocr_lang)
                except Exception:
                    extracted_text = pytesseract.image_to_string(img, lang='eng')

            cleaned_text = extracted_text.strip()
            # If no letters or less than 3 readable characters found (support Latin and Devanagari)
            import re
            letters_only = re.sub(r'[^a-zA-Z\u0900-\u097F]', '', cleaned_text)
            if not cleaned_text or len(letters_only) < 3:
                return "No readable ingredient text could be detected from the image. Please ensure the label is well-lit, clearly in focus, and flat, or paste the ingredient text directly."
            return cleaned_text

        except (TesseractNotFoundError, TesseractConfigError):
            raise
        except pytesseract.pytesseract.TesseractNotFoundError:
            if os.name == 'nt' or sys.platform.startswith('win'):
                raise TesseractNotFoundError(
                    "Tesseract OCR is not installed or could not be located. "
                    "Install Tesseract OCR for Windows, then configure TESSERACT_CMD with the "
                    "full path to tesseract.exe or add its installation directory to your system PATH. "
                    "Restart the application and try again."
                )
            else:
                raise TesseractNotFoundError(
                    "Tesseract OCR is not installed or could not be located on this Linux system. "
                    "Ensure tesseract-ocr is installed in your Dockerfile (apt-get install -y tesseract-ocr tesseract-ocr-eng) "
                    "or set TESSERACT_CMD to the tesseract binary location. On Render, deploy using Docker runtime."
                )
        except Exception as exc:
            raise RuntimeError(
                f"OCR processing failed: {exc}. "
                "Try using a higher-quality image or paste the ingredient text directly."
            )
