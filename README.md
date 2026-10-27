# Food Ingredient Safety Scanner (IngredientIQ) 🥦🔍

> **A friendly, modern web application to decode food labels, detect harmful additives and allergens, and align food choices with your diet.**  
> Built with Flask, Bootstrap 5, SQLite, SQLAlchemy, OpenCV, Tesseract OCR, and RapidFuzz.

---

## 📋 Overview

The **Food Ingredient Safety Scanner** helps consumers understand what is actually inside packaged foods. Users can either snap/upload a food package label image or paste raw ingredient text. The system extracts the text, cleans and normalizes it, cross-references each ingredient against an additive database, identifies allergens, checks for dietary conflicts, and computes a transparent safety rating.

### Key Real Features:
- **Image & Text Label Scanning**: Upload an image (PNG, JPG, WEBP, BMP, TIFF) or directly paste ingredients text into the scanner.
- **OCR Extraction**: Automated image preprocessing with OpenCV and text recognition via Tesseract OCR.
- **Intelligent Ingredient Matching**: Multi-layer matching supporting canonical names, case-insensitivity, international E-numbers (e.g., `E621`), common aliases (e.g., `sodium glutamate`, `whey`), and fuzzy typo tolerance (e.g., `caseen` → `Milk powder`).
- **My Allergies / Diet Conflict Checking**:
  - Allergy detection for Peanuts, Milk, Gluten, Soy, Eggs, Tree nuts, Fish, Shellfish, and Sesame.
  - Dietary checks for Vegetarian and Vegan diets.
  - Personal conflicts immediately override the displayed safety verdict to **Avoid** while preserving the raw ingredient score.
- **Transparent Safety Scoring**: Calculates an objective 0–100 safety score:
  - **Clean & Safe** ($\ge 85$)
  - **Moderate Caution** ($60 - 84$)
  - **High Risk** ($< 60$)
- **Scan History**: Completed scans are permanently recorded in a SQLite database with timestamp, unique image reference, extracted text, score, and verdict.
- **Ingredient Search Directory**: Instant interactive search to check safety ratings, descriptions, health effects, and aliases for additives and ingredients.
- **PDF Report Generation**: Download detailed, shareable safety reports for any completed scan.

---

## 💻 Prerequisites

Before running the application, make sure you have:
1. **Python 3.10+** (Tested on Python 3.12). Check version with:
   ```powershell
   python --version
   ```
2. **pip** (Python package manager, bundled with standard Python installations).
3. **A Modern Web Browser** (Google Chrome, Mozilla Firefox, Microsoft Edge, or Safari).
4. **Tesseract OCR (Optional)**: Needed only if you wish to scan physical label images via OCR. Text scanning works immediately without Tesseract.

---

## 🛠️ Step-by-Step Installation (Windows & PowerShell)

### 1. Clone or Open the Project
Open PowerShell and navigate to the project directory:
```powershell
cd c:\Users\Kartik\OneDrive\Desktop\3rdsem\3rd-sem-project
```

### 2. Create and Activate a Virtual Environment
```powershell
# Create virtual environment named .venv
python -m venv .venv

# Activate virtual environment in PowerShell
.\.venv\Scripts\Activate.ps1
```

> **PowerShell Execution Policy Tip**: If you see an error saying `script execution is disabled on this system`, run:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```
> Alternatively, you can run commands directly through the virtual environment binary without activating:
> ```powershell
> .\.venv\Scripts\python.exe run.py
> ```

### 3. Install Required Dependencies
```powershell
pip install -r requirements.txt
```

### 4. Initialize and Seed the Database
Seed the SQLite database with the 80-ingredient catalog:
```powershell
python database.py
```
*Note: This command is idempotent — you can run it multiple times safely without creating duplicate entries.*

---

## 📷 Tesseract OCR Setup on Windows

Tesseract OCR enables physical label scanning from images.

> **Important**: Text-only scanning works **100% out of the box** even without Tesseract installed! You only need Tesseract if you plan to upload and scan image files.

### 1. Install a Trusted Windows Build of Tesseract OCR
- Download the official Windows 64-bit installer from the UB-Mannheim project:  
  [UB-Mannheim Tesseract Installer](https://github.com/UB-Mannheim/tesseract/wiki)
- Run the installer.

### 2. Locate the Actual `tesseract.exe` File
The default installation directory is:
```text
C:\Program Files\Tesseract-OCR\tesseract.exe
```
*(If installed for only your user account, it may be at `C:\Users\<YourUsername>\AppData\Local\Programs\Tesseract-OCR\tesseract.exe`).*

### 3. Configure Tesseract on Windows

The application supports both configuration methods:

#### Method A: Persistent Configuration via `.env` (Recommended)
Create or edit your local `.env` file in the project root:
```ini
# .env
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```
*(No quotation marks needed in `.env`. The application automatically loads `.env` on startup).*

#### Method B: Add to Windows System PATH
1. Open Windows Search, type **Environment Variables**, and select **Edit the system environment variables**.
2. Click **Environment Variables...**
3. Under *User variables* or *System variables*, select **Path** and click **Edit**.
4. Click **New** and add the directory containing `tesseract.exe` (e.g. `C:\Program Files\Tesseract-OCR`).
5. Click **OK** to save.

#### Method C: Temporary PowerShell Session Setting
For quick testing in the current PowerShell terminal:
```powershell
$env:TESSERACT_CMD = "C:\Program Files\Tesseract-OCR\tesseract.exe"
```
> **Note**: Setting `$env:TESSERACT_CMD` in PowerShell applies **only to the current terminal session**. Once you close the window, the setting is lost. For a persistent setup, use **Method A (`.env`)** or **Method B (System PATH)**.

### 4. Restart the Terminal and Application
After adding Tesseract to PATH or editing `.env`, close and reopen your PowerShell terminal so the new environment variables take effect, then restart the app:
```powershell
python run.py
```

### 5. Verify the Installation
To verify that Tesseract is accessible from your command line:
```powershell
tesseract --version
```
Expected output:
```text
tesseract v5.5.x...
 leptonica-1.8x...
```

---

## 🚀 Running the Application

Start the local Flask development server:
```powershell
python run.py
```

You should see:
```text
 * Running on http://127.0.0.1:5000 (Press CTRL+C to quit)
```

Open your browser and visit:
```text
http://127.0.0.1:5000
```

### Troubleshooting Common Issues
- **Port 5000 is already in use**: If another application is running on port 5000, edit `run.py` and change `port=5000` to `port=5001`, then restart.
- **ModuleNotFoundError**: Ensure your virtual environment is active (`(.venv)` prefix in terminal) or run `.\.venv\Scripts\pip.exe install -r requirements.txt`.
- **Image upload shows Tesseract warning**: Install Tesseract OCR using the instructions above, or use the direct text input area on `/scan` to paste ingredients.

---

## 🧪 Running Automated Tests

The project includes automated tests using Python's built-in `unittest` framework. All tests run in isolation using an in-memory SQLite database (`sqlite:///:memory:`) and **never** modify or delete your real database (`instance/ingredientiq.db`).

Run the complete test suite with:
```powershell
python -m unittest discover -s tests -v
```

*(You can also run tests with `pytest` if preferred).*

### What the Tests Cover:
- **Text Cleaning (`TestTextCleaning`)**:
  - Removing excessive whitespace and extra spaces.
  - Safely handling empty strings and `None` inputs without throwing exceptions.
  - Normalizing text with line breaks (`\r\n`).
  - Preserving ingredient names and international E-numbers (e.g. `Ingredients:  Wheat Flour,  Sugar,  E621`).
- **Ingredient Matching (`TestIngredientMatching`)**:
  - Exact name matching (100% confidence).
  - Case-insensitive matching.
  - E-number matching (e.g. `E621` → Monosodium glutamate).
  - Alias matching (e.g. `sodium glutamate` → Monosodium glutamate, `whey` → Milk powder).
  - Fuzzy matching for typos (e.g. `caseen` → Milk powder).
  - Unrelated inputs (prevents false-positive matches).
  - Empty or whitespace ingredient searches.
- **Safety Scoring & Overrides (`TestSafetyScoring`)**:
  - Baseline score for empty/clean inputs (100).
  - Deductions based on ingredient classifications (Safe = 0, Caution = -15, Harmful = -35).
  - Deduplicating repeated ingredients to prevent unfair penalty inflation.
  - Clamping scores strictly between 0 and 100.
  - Threshold agreement (`Clean & Safe`, `Moderate Caution`, `High Risk`).
  - Personal allergy and diet overrides: sets verdict to `Avoid` without changing underlying calculated score.
- **Routes & Security (`TestAppRoutesAndSecurity`)**:
  - HTTP 200 response on all navigation routes.
  - Custom 404 error page.
  - Scan persistence and history verification.
  - File upload security (rejects fake images masquerading with image extensions).
  - Access control: verifies that private user scans cannot be accessed by unauthorized guests (HTTP 403).

---

## 📂 Project Directory Structure

```text
3rd-sem-project/
├── app/
│   ├── __init__.py           # Flask application factory (create_app, db, error handlers)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── ingredient.py     # SQLAlchemy models: Ingredient and Scan (scans table)
│   │   └── user.py           # SQLAlchemy User model with scans relationship
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── main.py           # Routes: /, /scan, /history, /search, /admin, reports
│   │   └── auth.py           # Routes: login, register, logout
│   ├── services/
│   │   ├── __init__.py
│   │   ├── analyzer_service.py # Text cleaning, RapidFuzz matching, scoring algorithm
│   │   ├── ocr_service.py    # OpenCV preprocessing & Tesseract text extraction
│   │   └── report_service.py # ReportLab PDF report generation
│   ├── static/
│   │   ├── css/style.css     # Custom responsive CSS and component styling
│   │   ├── js/main.js        # Drag-and-drop file upload, spinner, client validation
│   │   └── uploads/          # Directory where user uploaded images are saved
│   └── templates/            # Bootstrap 5 Jinja2 templates
│       ├── base.html         # Common layout, responsive navbar, and dynamic footer
│       ├── index.html        # Landing page with hero section and feature cards
│       ├── scan.html         # Scan interface, allergy/diet checkboxes, and results
│       ├── history.html      # Chronological scan history table with score badges
│       ├── search.html       # Ingredient search directory with filters
│       ├── admin.html        # System health and architecture metrics
│       ├── auth/             # Login and registration templates
│       └── errors/           # Custom 403, 404, and 500 error pages
├── data/
│   └── ingredients.csv       # 80-ingredient catalog with E-numbers, allergens & diet tags
├── instance/
│   └── ingredientiq.db       # Local SQLite database storing ingredients and scans
├── tests/
│   ├── __init__.py
│   ├── test_analyzer.py      # Unittest suite: text cleaning, matching, and scoring
│   ├── test_basic.py         # Unittest suite: basic workflows, CSV seeding, and database queries
│   └── test_routes.py        # Unittest suite: routes, file upload security, and access control
├── .env.example              # Example environment configuration
├── .gitignore                # Git exclusions (database, uploads, .env, venv)
├── config.py                 # Multi-environment configuration (Dev, Test, Prod)
├── database.py               # Table creation & idempotent CSV seed script
├── requirements.txt          # Python dependencies list
├── run.py                    # Application launch script
└── README.md                 # Project documentation
```

---

## 🔒 Database & File Upload Handling

### 1. SQLite Database (`instance/ingredientiq.db`)
- The SQLite database file resides in the `instance/` folder.
- Contains two primary tables:
  - `ingredients`: 80 food ingredients, E-numbers, safety classifications, allergen tags, and diet flags.
  - `scans`: Historical records of completed scans including product name, timestamp, score, verdict, and extracted text.
- The `instance/` directory and `*.db` files are strictly included in `.gitignore` to prevent committing local data.

### 2. Uploaded Images (`app/static/uploads/`)
- When a user uploads a label photo, a safe, collision-proof filename is generated:
  `{uuid4[:8]}_{secure_filename}`
- **Security Validation**:
  - File extension is verified against `ALLOWED_EXTENSIONS`.
  - The file stream is inspected with Pillow (`PIL.Image.open().verify()`) to prevent masqueraded executable scripts.
  - File size is restricted by `MAX_CONTENT_LENGTH` (16 MB).
- The `app/static/uploads/*` pattern is ignored in `.gitignore` with `.gitkeep` preserving directory existence.

---

## 📄 License
This project was developed for the 3rd Semester Academic Project. Released under the MIT License.
