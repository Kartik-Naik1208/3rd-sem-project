import io
import os
import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw

from app import create_app, db
from app.services.ocr_service import (
    OCRService,
    TesseractNotFoundError,
    TesseractConfigError,
    find_tesseract_cmd,
    _check_tesseract,
)


class TestTesseractConfiguration(unittest.TestCase):
    """Test Tesseract OCR detection, path validation, and error messaging."""

    def test_explicit_valid_path(self):
        """A valid existing path configured via parameter or environment is accepted."""
        # Using a known existing file on the system (e.g. this test file or actual tesseract if present)
        current_file = os.path.abspath(__file__)
        with patch.dict(os.environ, {'TESSERACT_CMD': current_file}):
            resolved = find_tesseract_cmd()
            self.assertEqual(resolved, os.path.normpath(current_file))

    def test_explicit_invalid_path_raises_config_error(self):
        """An invalid path raises TesseractConfigError with a clear actionable message."""
        fake_path = r"C:\NonExistentDir12345\tesseract.exe"
        with patch.dict(os.environ, {'TESSERACT_CMD': fake_path}):
            with self.assertRaises(TesseractConfigError) as ctx:
                find_tesseract_cmd()
            msg = str(ctx.exception)
            self.assertIn("The configured Tesseract OCR path could not be found", msg)
            self.assertIn(fake_path, msg)

    def test_quoted_path_handling(self):
        """Paths enclosed in single or double quotes are cleaned and handled properly."""
        current_file = os.path.abspath(__file__)
        quoted_path = f'"{current_file}"'
        with patch.dict(os.environ, {'TESSERACT_CMD': quoted_path}):
            resolved = find_tesseract_cmd()
            self.assertEqual(resolved, os.path.normpath(current_file))

    def test_path_lookup_via_system_path(self):
        """When TESSERACT_CMD is unset, locates executable from system PATH."""
        with patch.dict(os.environ, {'TESSERACT_CMD': ''}):
            with patch('shutil.which', return_value=r"C:\Custom\tesseract.exe"):
                resolved = find_tesseract_cmd()
                self.assertEqual(resolved, os.path.normpath(r"C:\Custom\tesseract.exe"))

    def test_tesseract_not_found_message_format(self):
        """When Tesseract cannot be found anywhere, raises TesseractNotFoundError with exact message."""
        with patch.dict(os.environ, {'TESSERACT_CMD': ''}):
            with patch('shutil.which', return_value=None):
                with patch('os.path.isfile', return_value=False):
                    with self.assertRaises(TesseractNotFoundError) as ctx:
                        find_tesseract_cmd()
                    msg = str(ctx.exception)
                    expected = (
                        "Tesseract OCR is not installed or could not be located. "
                        "Install Tesseract OCR for Windows, then configure TESSERACT_CMD with the "
                        "full path to tesseract.exe or add its installation directory to your system PATH. "
                        "Restart the application and try again."
                    )
                    self.assertEqual(msg, expected)

    def test_is_tesseract_available_returns_boolean_without_crashing(self):
        """is_tesseract_available should return a boolean and never raise an unhandled exception."""
        with patch('app.services.ocr_service.find_tesseract_cmd', side_effect=TesseractNotFoundError("not found")):
            self.assertFalse(OCRService.is_tesseract_available())

        with patch('app.services.ocr_service.find_tesseract_cmd', return_value=r"C:\fake\tesseract.exe"):
            with patch('pytesseract.get_tesseract_version', return_value="5.5.0"):
                self.assertTrue(OCRService.is_tesseract_available())


class TestOCRWorkflowAndTextFallback(unittest.TestCase):
    """Test text scanning fallback when OCR is unavailable and image scanning when available."""

    def setUp(self):
        self.app = create_app('testing')
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_text_scanning_works_when_tesseract_unavailable(self):
        """Text-based scanning continues to function normally even if Tesseract is missing."""
        with patch('app.services.ocr_service.OCRService.is_tesseract_available', return_value=False):
            response = self.client.post('/scan', data={
                'product_name': 'Orange Soda',
                'raw_text': 'Carbonated Water, Sugar, Citric Acid (E330), Tartrazine (E102)',
                'allergies': [],
                'diet': 'None'
            }, follow_redirects=True)

            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertIn('Orange Soda', html)
            self.assertIn('Identified Ingredients Breakdown', html)
            self.assertIn('Citric acid', html)
            self.assertIn('Tartrazine', html)
            # Caution penalty for Tartrazine (-15) -> Score 85 -> Clean & Safe
            self.assertTrue('Clean &amp; Safe' in html or 'Clean & Safe' in html)

    def test_image_scan_shows_friendly_error_when_tesseract_missing(self):
        """Uploading an image when Tesseract is missing displays friendly error without 500 crash."""
        # Create a valid minimal PNG
        img = Image.new('RGB', (100, 100), color=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)

        with patch('app.services.ocr_service.find_tesseract_cmd', side_effect=TesseractNotFoundError(
            "Tesseract OCR is not installed or could not be located. "
            "Install Tesseract OCR for Windows, then configure TESSERACT_CMD with the "
            "full path to tesseract.exe or add its installation directory to your system PATH. "
            "Restart the application and try again."
        )):
            data = {
                'product_name': 'Label Image Test',
                'label_image': (buf, 'label.png')
            }
            response = self.client.post('/scan', data=data, content_type='multipart/form-data', follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertIn("Tesseract OCR is not installed or could not be located", html)

    def test_image_scan_with_invalid_tesseract_cmd_shows_path_error(self):
        """Uploading an image when TESSERACT_CMD is invalid explains the configured path failed."""
        img = Image.new('RGB', (100, 100), color=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)

        with patch('app.services.ocr_service.find_tesseract_cmd', side_effect=TesseractConfigError(
            "The configured Tesseract OCR path could not be found: 'C:\\Invalid\\tesseract.exe'. "
            "Please verify that the path points to a valid tesseract.exe executable, "
            "or remove TESSERACT_CMD to let the system detect it automatically."
        )):
            data = {
                'product_name': 'Label Image Test',
                'label_image': (buf, 'label.png')
            }
            response = self.client.post('/scan', data=data, content_type='multipart/form-data', follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertIn("The configured Tesseract OCR path could not be found", html)

    def test_real_tesseract_ocr_if_installed(self):
        """If Tesseract is actually installed at C:\\Program Files\\Tesseract-OCR\\tesseract.exe, test end-to-end OCR."""
        default_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if os.path.isfile(default_path):
            img = Image.new('RGB', (300, 80), color=(255, 255, 255))
            draw = ImageDraw.Draw(img)
            draw.text((10, 25), "Sugar, Salt", fill=(0, 0, 0))
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)

            data = {
                'product_name': 'Real OCR Snack',
                'label_image': (buf, 'real_ocr.png')
            }
            response = self.client.post('/scan', data=data, content_type='multipart/form-data', follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertIn('Image successfully processed via OCR', html)


if __name__ == '__main__':
    unittest.main()
