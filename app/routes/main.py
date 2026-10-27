import os
import uuid
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, send_file, abort
from flask_login import current_user
from werkzeug.utils import secure_filename
from app import db
from app.models.ingredient import Ingredient, Scan, ScanRecord
from app.services.ocr_service import OCRService, TesseractNotFoundError, TesseractConfigError
from app.services.analyzer_service import IngredientAnalyzer
from app.services.report_service import ReportGenerator

main_bp = Blueprint('main', __name__)

analyzer = IngredientAnalyzer()


def allowed_file(filename):
    allowed = current_app.config.get('ALLOWED_EXTENSIONS', {'png', 'jpg', 'jpeg', 'webp'})
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed


@main_bp.route('/')
def index():
    """Landing page introducing IngredientIQ and its core capabilities."""
    featured_ingredients = [
        {'name': 'Citric Acid (E330)', 'tag': 'Safe', 'class': 'success', 'desc': 'Natural citrus preservative & flavor.'},
        {'name': 'Soy Lecithin (E322)', 'tag': 'Allergen', 'class': 'info', 'desc': 'Emulsifier derived from soy beans.'},
        {'name': 'Tartrazine (E102)', 'tag': 'Caution', 'class': 'warning', 'desc': 'Azo dye linked to hyperactivity.'},
        {'name': 'Sodium Nitrite (E250)', 'tag': 'Avoid', 'class': 'danger', 'desc': 'Curing salt linked to nitrosamines.'}
    ]
    return render_template('index.html', featured_ingredients=featured_ingredients)


@main_bp.route('/scan', methods=['GET', 'POST'])
def scan():
    """Scan interface supporting image upload with OCR or direct text analysis."""
    analysis_result = None
    extracted_text = ""
    product_name = "Sample Product"
    unique_name = None  # track uploaded filename for DB record
    selected_allergies = []
    selected_diet = "None"

    if request.method == 'POST':
        product_name = request.form.get('product_name', 'Scanned Item').strip() or 'Scanned Item'
        raw_text_input = request.form.get('raw_text', '').strip()
        uploaded_file = request.files.get('label_image')
        selected_allergies = request.form.getlist('allergies')
        selected_diet = request.form.get('diet', 'None').strip() or 'None'

        # 1. Image OCR pipeline
        if uploaded_file and uploaded_file.filename != '':
            if allowed_file(uploaded_file.filename):
                # Verify file content / magic bytes using Pillow to prevent disguised files
                try:
                    from PIL import Image
                    img = Image.open(uploaded_file.stream)
                    img.verify()
                    # Rewind stream position after verification
                    uploaded_file.stream.seek(0)
                except Exception:
                    flash('Invalid or corrupted image file.', 'danger')
                    return redirect(url_for('main.scan'))

                safe_name = secure_filename(uploaded_file.filename)
                unique_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
                save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_name)
                uploaded_file.save(save_path)

                try:
                    ocr = OCRService(tesseract_cmd=current_app.config.get('TESSERACT_CMD'))
                    extracted_text = ocr.extract_text(save_path)
                    flash('Image successfully processed via OCR.', 'success')
                except (TesseractNotFoundError, TesseractConfigError) as exc:
                    flash(str(exc), 'danger')
                    return redirect(url_for('main.scan'))
                except RuntimeError as exc:
                    flash(str(exc), 'danger')
                    return redirect(url_for('main.scan'))
            else:
                flash('Unsupported image format. Allowed: PNG, JPG, JPEG, WEBP, BMP, TIFF.', 'danger')
                return redirect(url_for('main.scan'))
        elif raw_text_input:
            extracted_text = raw_text_input
        else:
            flash('Please upload an image or paste ingredient label text.', 'warning')
            return redirect(url_for('main.scan'))

        # 2. Ingredient & Allergen Analysis
        if extracted_text:
            # Ensure catalog is loaded from DB (lazy refresh after seeding)
            analyzer.refresh_catalog()
            analysis_result = analyzer.analyze(
                extracted_text,
                user_allergies=selected_allergies,
                user_diet=selected_diet
            )

            # Persist scan to `scans` table in SQLite
            try:
                record = Scan(
                    user_id=current_user.id if current_user.is_authenticated else None,
                    product_name=product_name,
                    image_filename=unique_name,
                    extracted_text=extracted_text,
                    score=analysis_result['safety_score'],
                    verdict=analysis_result['summary'],
                    scan_date=datetime.now(timezone.utc),
                    detected_ingredients=analysis_result['detected_ingredients'],
                    flagged_allergens=", ".join(analysis_result['flagged_allergens']),
                    personal_conflicts=analysis_result.get('personal_conflicts', [])
                )
                db.session.add(record)
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                # Continue displaying result even if DB write fails

    return render_template(
        'scan.html',
        analysis_result=analysis_result,
        extracted_text=extracted_text,
        product_name=product_name,
        selected_allergies=selected_allergies,
        selected_diet=selected_diet
    )


@main_bp.route('/scan/<int:scan_id>')
@main_bp.route('/history/<int:scan_id>')
def view_scan(scan_id):
    """Displays the result page for a specific past scan by database ID."""
    scan_record = db.session.get(Scan, scan_id)
    if scan_record is None:
        return render_template('errors/404.html'), 404

    # Access control: user-associated scans can only be viewed by the owner
    if scan_record.user_id is not None:
        if not current_user.is_authenticated or current_user.id != scan_record.user_id:
            abort(403)

    # Build analysis_result dict from stored database fields without recalculating
    v_lower = (scan_record.verdict or '').lower()
    if 'avoid' in v_lower or 'high' in v_lower:
        badge_class = 'danger'
    elif 'caution' in v_lower:
        badge_class = 'warning'
    else:
        badge_class = 'success'

    flagged_allergens = [a.strip() for a in scan_record.flagged_allergens.split(',') if a.strip()] if scan_record.flagged_allergens else []
    personal_conflicts = scan_record.personal_conflicts
    has_conflict = len(personal_conflicts) > 0 or scan_record.verdict == 'Avoid'

    detected_list = scan_record.detected_ingredients
    caution_count = sum(1 for i in detected_list if i.get('safety_rating') == 'Caution' or i.get('safety_level') == 'Caution')
    harmful_count = sum(1 for i in detected_list if i.get('safety_rating') == 'Harmful' or i.get('safety_level') == 'Harmful')
    avoid_count = sum(1 for i in detected_list if i.get('safety_rating') == 'Avoid' or i.get('safety_level') == 'Avoid')

    analysis_result = {
        'summary': scan_record.verdict,
        'badge_class': badge_class,
        'safety_score': scan_record.score,
        'has_conflict': has_conflict,
        'personal_conflicts': personal_conflicts,
        'detected_ingredients': detected_list,
        'flagged_allergens': flagged_allergens,
        'stats': {
            'total_detected': len(detected_list),
            'caution_count': caution_count,
            'avoid_count': avoid_count,
            'harmful_count': harmful_count,
            'allergen_count': len(flagged_allergens)
        }
    }

    return render_template(
        'scan.html',
        analysis_result=analysis_result,
        extracted_text=scan_record.extracted_text,
        product_name=scan_record.product_name,
        saved_scan=scan_record
    )


@main_bp.route('/history')
def history():
    """Scan history page showing previous scans in reverse chronological order, newest first."""
    page = request.args.get('page', 1, type=int)
    per_page = 15

    try:
        if current_user.is_authenticated:
            query = Scan.query.filter_by(user_id=current_user.id)
        else:
            query = Scan.query

        pagination = query.order_by(Scan.scan_date.desc(), Scan.id.desc()).paginate(page=page, per_page=per_page, error_out=False)
        records = pagination.items
    except Exception:
        pagination = None
        records = []

    return render_template('history.html', records=records, pagination=pagination)


@main_bp.route('/search')
def search():
    """Ingredient directory and search page with exact, partial, and fuzzy matching."""
    query = request.args.get('q', '').strip()
    category = request.args.get('category', '').strip()
    safety = request.args.get('safety', '').strip()

    analyzer.refresh_catalog()

    if query:
        # Use our intelligent search (exact -> partial -> fuzzy matching)
        results = analyzer.search_ingredients(query)
    else:
        # Load catalog from database / fallback
        try:
            db_items = Ingredient.query.all()
            results = [i.to_dict() for i in db_items] if db_items else analyzer.catalog
        except Exception:
            results = analyzer.catalog

    # Apply optional category and safety filters
    filtered_results = []
    for item in results:
        match = True
        if category:
            item_cat = (item.get('category') or '').lower()
            if item_cat != category.lower():
                match = False
        if safety and match:
            item_safety = (item.get('safety_level') or item.get('safety_rating') or '').lower()
            if item_safety != safety.lower():
                match = False
        if match:
            filtered_results.append(item)

    # Distinct categories for filter dropdown
    all_items = analyzer.catalog
    categories = sorted(list(set(i.get('category', 'General') for i in all_items if i.get('category'))))

    return render_template(
        'search.html',
        results=filtered_results,
        query=query,
        selected_category=category,
        selected_safety=safety,
        categories=categories
    )


@main_bp.route('/export-report/<int:scan_id>')
def export_report(scan_id):
    """Generates and downloads a PDF safety report for a scan record."""
    record = db.session.get(Scan, scan_id)
    if record is None:
        abort(404)

    # Access control: user-associated scans can only be exported by the owner
    if record.user_id is not None:
        if not current_user.is_authenticated or current_user.id != record.user_id:
            abort(403)

    analysis_data = {
        'summary': record.verdict,
        'flagged_allergens': [a.strip() for a in record.flagged_allergens.split(',')] if record.flagged_allergens else [],
        'detected_ingredients': record.detected_ingredients
    }
    user_name = record.user.username if record.user else "Guest User"
    pdf_buffer = ReportGenerator.generate_pdf(record.product_name, analysis_data, user_name)

    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f"IngredientIQ_Report_{record.id}.pdf",
        mimetype='application/pdf'
    )


@main_bp.route('/admin')
def admin():
    """Admin dashboard overview."""
    total_users = 0
    total_scans = 0
    total_ingredients = len(analyzer.catalog)

    try:
        from app.models.user import User
        total_users = User.query.count()
        total_scans = ScanRecord.query.count()
        db_ing_count = Ingredient.query.count()
        if db_ing_count > 0:
            total_ingredients = db_ing_count
    except Exception:
        pass

    system_status = {
        'database': 'Connected (SQLite)',
        'ocr_engine': 'OpenCV + Tesseract OCR Ready' if OCRService.is_tesseract_available(current_app.config.get('TESSERACT_CMD')) else 'Tesseract Not Detected (Text Scanning Available)',
        'fuzzy_matcher': 'RapidFuzz Active',
        'pdf_reporter': 'ReportLab Ready'
    }

    return render_template(
        'admin.html',
        total_users=total_users,
        total_scans=total_scans,
        total_ingredients=total_ingredients,
        system_status=system_status
    )
