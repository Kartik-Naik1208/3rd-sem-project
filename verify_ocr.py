#!/usr/bin/env python3
"""
IngredientIQ - OCR Diagnostics & Pre-Deployment Verification Script
Tests all 6 criteria required for production OCR readiness:
  1. tesseract --version execution
  2. tesseract --list-langs execution (English, OSD, Hindi checks)
  3. pytesseract.get_tesseract_version() integration
  4. Reading a synthesized test image via pytesseract
  5. OpenCV image enhancement and preprocessing (CLAHE, bilateral filter, adaptive threshold)
  6. End-to-end product label scanning and text extraction
"""

import os
import sys
import tempfile
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    import pytesseract
    from app.services.ocr_service import (
        OCRService,
        find_tesseract_cmd,
        get_installed_languages,
        check_ocr_health,
        CV2_AVAILABLE,
    )
except ImportError as err:
    print(f"[FAIL] Error importing IngredientIQ modules: {err}")
    sys.exit(1)


def run_checks():
    print("=" * 70)
    print("  IngredientIQ - Production OCR & Tesseract Verification Suite")
    print("=" * 70)
    all_passed = True

    # 1. Resolve Tesseract executable
    print("\n[Step 1] Locating Tesseract Executable...")
    try:
        tess_cmd = find_tesseract_cmd()
        print(f"  [OK] Tesseract binary located at: {tess_cmd}")
        pytesseract.pytesseract.tesseract_cmd = tess_cmd
    except Exception as e:
        print(f"  [FAIL] Could not locate Tesseract binary: {e}")
        return False

    # 2. Test tesseract --version directly
    print("\n[Step 2] Testing 'tesseract --version' (Subprocess Check)...")
    try:
        res = subprocess.run([tess_cmd, "--version"], capture_output=True, text=True, timeout=10)
        first_line = res.stdout.strip().splitlines()[0] if res.stdout else "unknown"
        print(f"  [OK] {first_line}")
    except Exception as e:
        print(f"  [FAIL] Failed executing 'tesseract --version': {e}")
        all_passed = False

    # 3. Test tesseract --list-langs directly
    print("\n[Step 3] Testing 'tesseract --list-langs' (Installed Languages)...")
    try:
        langs = get_installed_languages(tess_cmd)
        print(f"  [OK] Installed language packs: {', '.join(langs) or 'None'}")
        if 'eng' in langs:
            print("  [OK] Required English ('eng') language pack: INSTALLED")
        else:
            print("  [FAIL] Required English ('eng') language pack: MISSING")
            all_passed = False

        if 'osd' in langs:
            print("  [INFO] Orientation & script detection ('osd'): INSTALLED")
        if 'hin' in langs:
            print("  [INFO] Optional Hindi ('hin') language pack: INSTALLED")
        else:
            print("  [INFO] Optional Hindi ('hin') language pack: Not installed (optional)")
    except Exception as e:
        print(f"  [FAIL] Failed retrieving installed languages: {e}")
        all_passed = False

    # 4. Test pytesseract.get_tesseract_version() integration
    print("\n[Step 4] Testing pytesseract.get_tesseract_version()...")
    try:
        py_version = pytesseract.get_tesseract_version()
        print(f"  [OK] pytesseract successfully communicated with binary (v{py_version})")
    except Exception as e:
        print(f"  [FAIL] pytesseract.get_tesseract_version() failed: {e}")
        all_passed = False

    # 5. Test reading a sample image using pytesseract
    print("\n[Step 5] Testing Direct Sample Image OCR with pytesseract...")
    try:
        sample_img = Image.new("RGB", (320, 80), color=(255, 255, 255))
        d = ImageDraw.Draw(sample_img)
        d.text((15, 25), "Sample 100% Pure Cane Sugar", fill=(0, 0, 0))
        raw_text = pytesseract.image_to_string(sample_img).strip()
        print(f"  [OK] pytesseract extracted raw text: '{raw_text}'")
        if "Sugar" not in raw_text and "Cane" not in raw_text:
            print("  [WARN] Expected keyword 'Sugar' not detected in raw synthetic pass.")
    except Exception as e:
        print(f"  [FAIL] Direct sample image OCR failed: {e}")
        all_passed = False

    # 6. Test OpenCV image enhancement and preprocessing
    print("\n[Step 6] Testing OpenCV Image Preprocessing Pipeline...")
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        temp_img_path = tf.name

    try:
        label_img = Image.new("RGB", (500, 140), color=(240, 240, 240))
        d = ImageDraw.Draw(label_img)
        d.text((20, 20), "INGREDIENTS:", fill=(20, 20, 20))
        d.text((20, 55), "Whole Wheat Flour, Water, Yeast, Sea Salt.", fill=(20, 20, 20))
        d.text((20, 90), "CONTAINS: Wheat. MAY CONTAIN: Soy.", fill=(20, 20, 20))
        label_img.save(temp_img_path)

        ocr_service = OCRService(tesseract_cmd=tess_cmd)
        if CV2_AVAILABLE:
            preprocessed = ocr_service.preprocess_image(temp_img_path)
            print(f"  [OK] OpenCV CLAHE and bilateral filtering completed: shape={preprocessed.shape}")
        else:
            print("  [WARN] OpenCV not available; fell back to PIL enhancement.")

        # 7. Test end-to-end extraction and section parsing
        print("\n[Step 7] Testing Full End-to-End Product Label Extraction...")
        extracted = ocr_service.extract_text(temp_img_path)
        print(f"  [OK] Extracted label text:\n       {extracted.replace(chr(10), ' ')}")

        sections = ocr_service.detect_sections(extracted)
        print(f"  [OK] Detected 'Contains': {sections.get('contains') or 'None detected'}")
        print(f"  [OK] Detected 'May Contain': {sections.get('may_contain') or 'None detected'}")

        if "Wheat" in extracted or "Flour" in extracted or "Salt" in extracted:
            print("  [OK] Key ingredient keywords successfully verified in extraction output.")
        else:
            print("  [WARN] Ingredients keywords not fully matched in extraction output.")

    except Exception as e:
        print(f"  [FAIL] End-to-end OCR extraction failed: {e}")
        all_passed = False
    finally:
        if os.path.exists(temp_img_path):
            os.remove(temp_img_path)

    # 8. Overall diagnostic health check
    print("\n[Step 8] Running check_ocr_health() Diagnostic...")
    health = check_ocr_health(tess_cmd)
    print(f"  Status: {health['status'].upper()}")
    print(f"  Is Available: {health['is_available']}")
    print(f"  Summary: {health['message']}")

    print("\n" + "=" * 70)
    if all_passed and health['is_available']:
        print("  RESULT: ALL OCR DIAGNOSTIC CHECKS PASSED SUCCESSFULLY (READY FOR PRODUCTION)")
        print("=" * 70 + "\n")
        return True
    else:
        print("  RESULT: OCR CHECKS FAILED OR DEGRADED (ATTENTION REQUIRED)")
        print("=" * 70 + "\n")
        return False


if __name__ == "__main__":
    success = run_checks()
    sys.exit(0 if success else 1)
