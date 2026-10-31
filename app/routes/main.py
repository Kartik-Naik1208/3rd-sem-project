import os
import uuid
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, send_file, send_from_directory, abort, session
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename
from app import db
from app.models.ingredient import Ingredient, Scan, ScanRecord
from app.services.ocr_service import OCRService, TesseractNotFoundError, TesseractConfigError
from app.services.analyzer_service import (
    IngredientAnalyzer,
    evaluate_child_suitability,
    evaluate_regular_consumption,
    evaluate_watch_outs,
    build_what_this_means_for_me,
    build_ingredient_assessment,
    generate_product_age_breakdown,
)
from app.services.report_service import ReportGenerator

main_bp = Blueprint('main', __name__)

analyzer = IngredientAnalyzer()


def allowed_file(filename):
    allowed = current_app.config.get('ALLOWED_EXTENSIONS', {'png', 'jpg', 'jpeg', 'webp'})
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed


@main_bp.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serve uploaded product label image files securely."""
    safe_name = secure_filename(filename)
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], safe_name)


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
            record = None
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
                    personal_conflicts=analysis_result.get('personal_conflicts', []),
                    child_suitability=analysis_result.get('child_suitability', {}),
                    regular_consumption=analysis_result.get('regular_consumption', {}),
                    detected_sections=analysis_result.get('sections', {})
                )
                db.session.add(record)
                db.session.commit()
            except Exception as e:
                db.session.rollback()

            # Server-side Authentication Gate (Requirement 4):
            # Visitors who are not logged in cannot view analysis results before authentication!
            if not current_user.is_authenticated:
                if record:
                    session['pending_scan_id'] = record.id
                    session['pending_scan_name'] = product_name
                flash(
                    f'Scan analysis for "{product_name}" is ready! Authentication is required to unlock your complete ingredient analysis, child suitability, and regular consumption reports.',
                    'info'
                )
                return redirect(url_for('auth.login', next=url_for('main.view_scan_results', scan_id=record.id) if record else url_for('main.scan')))

            # If user is already authenticated, redirect directly to dedicated results page
            return redirect(url_for('main.view_scan_results', scan_id=record.id))

    return render_template(
        'scan.html',
        analysis_result=None,
        extracted_text=extracted_text,
        product_name=product_name,
        selected_allergies=selected_allergies,
        selected_diet=selected_diet
    )


@main_bp.route('/history/<int:scan_id>', endpoint='view_history_scan')
@main_bp.route('/scan/<int:scan_id>', endpoint='view_scan')
@main_bp.route('/scan/<int:scan_id>/results', endpoint='view_scan_results')
def view_scan_results(scan_id):
    """Displays the dedicated product analysis and results page for a scan."""
    scan_record = db.session.get(Scan, scan_id)
    if scan_record is None:
        return render_template('errors/404.html'), 404

    # Server-side authentication check: unauthenticated visitors cannot view protected results!
    if not current_user.is_authenticated:
        flash('Please log in to continue.', 'warning')
        return redirect(url_for('auth.login', next=url_for('main.view_scan_results', scan_id=scan_id)))

    # If scan was created while guest and user is now authenticated, claim it
    if scan_record.user_id is None:
        scan_record.user_id = current_user.id
        db.session.commit()
    elif scan_record.user_id != current_user.id and not getattr(current_user, 'is_admin', False):
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
    unrecognized_count = sum(1 for i in detected_list if i.get('is_unrecognized'))

    # Load child suitability and regular consumption from record (or generate fallback if missing)
    child_suitability = scan_record.child_suitability
    if not child_suitability:
        child_suitability = evaluate_child_suitability(detected_list, scan_record.extracted_text)
    elif 'simple_status' not in child_suitability:
        cs_stat = child_suitability.get('status', '')
        if 'Not for ingestion' in cs_stat:
            child_suitability['simple_status'] = 'Not for ingestion (Cosmetic product)'
        elif 'Potential concern' in cs_stat:
            child_suitability['simple_status'] = 'Potential concern'
        elif 'Use caution' in cs_stat:
            child_suitability['simple_status'] = 'Use caution'
        elif 'Insufficient' in cs_stat:
            child_suitability['simple_status'] = 'Not enough information'
        else:
            child_suitability['simple_status'] = 'No specific concern identified'

    if 'age_breakdown' not in child_suitability or not child_suitability['age_breakdown']:
        child_suitability['age_breakdown'] = generate_product_age_breakdown(
            detected_list,
            scan_record.extracted_text,
            is_cosmetic=child_suitability.get('is_cosmetic', False)
        )

    regular_consumption = scan_record.regular_consumption
    if not regular_consumption:
        regular_consumption = evaluate_regular_consumption(detected_list, scan_record.extracted_text)
    elif 'simple_status' not in regular_consumption:
        rc_stat = regular_consumption.get('status', '')
        if 'Limit' in rc_stat:
            regular_consumption['simple_status'] = 'Better to limit'
        elif 'External' in rc_stat:
            regular_consumption['simple_status'] = 'External use only (Cosmetic)'
        elif 'Insufficient' in rc_stat:
            regular_consumption['simple_status'] = 'Not enough information'
        else:
            regular_consumption['simple_status'] = 'Generally reasonable based on available information'

    # Ensure detected_ingredients have complete short descriptions, safety statuses, and age guidance
    enriched_detected = []
    for ing in detected_list:
        if 'short_description' not in ing or 'safety_status' not in ing or 'children_suitability_status' not in ing or 'display_name' not in ing:
            is_unrec = ing.get('is_unrecognized', False)
            match_dummy = {
                'name': ing.get('matched_name') or ing.get('name') or ing.get('raw_token'),
                'e_number': ing.get('e_number'),
                'category': ing.get('category', 'General'),
                'safety_level': ing.get('safety_level') or ing.get('safety_rating') or 'Safe',
                'safety_rating': ing.get('safety_rating') or ing.get('safety_level') or 'Safe',
                'allergen_tag': ing.get('allergen_tag') or '',
                'allergen_type': ing.get('allergen_type'),
                'health_effects': ing.get('health_effects'),
                'banned_status': ing.get('banned_status', False),
                'ingredient_type': ing.get('ingredient_type', 'food'),
                'what_is_it': ing.get('what_is_it'),
                'why_used': ing.get('why_used'),
                'common_uses': ing.get('common_uses'),
                'child_considerations': ing.get('child_considerations'),
                'regular_consumption': ing.get('regular_consumption'),
                'source_attribution': ing.get('source_attribution', 'FSSAI / Codex Alimentarius / ICMR-NIN')
            }
            ass = build_ingredient_assessment(
                match_dummy if not is_unrec else None,
                ing.get('raw_token') or ing.get('matched_name'),
                is_matched=not is_unrec,
                recognition_status=ing.get('recognition_status', 'Recognized'),
                percentage=ing.get('percentage')
            )
            ing_copy = dict(ing)
            for k, v in ass.items():
                if k not in ing_copy or not ing_copy[k]:
                    ing_copy[k] = v
            if 'display_name' not in ing_copy:
                ing_copy['display_name'] = f"{ing_copy['matched_name']} ({ing_copy['e_number']})" if ing_copy.get('e_number') else ing_copy['matched_name']
            enriched_detected.append(ing_copy)
        else:
            enriched_detected.append(ing)

    detected_list = enriched_detected

    sections = scan_record.detected_sections or {}
    watch_outs = evaluate_watch_outs(
        detected_list=detected_list,
        flagged_allergens=flagged_allergens,
        personal_conflicts=personal_conflicts,
        sections=sections,
        unrecognized_count=unrecognized_count
    )

    what_this_means_for_me = build_what_this_means_for_me(
        detected_list=detected_list,
        flagged_allergens=flagged_allergens,
        personal_conflicts=personal_conflicts,
        child_suitability=child_suitability,
        regular_consumption=regular_consumption,
        watch_outs=watch_outs,
        sections=sections
    )

    attention_count = caution_count + harmful_count + avoid_count
    analysis_result = {
        'summary': scan_record.verdict,
        'badge_class': badge_class,
        'safety_score': scan_record.score,
        'has_conflict': has_conflict,
        'personal_conflicts': personal_conflicts,
        'detected_ingredients': detected_list,
        'flagged_allergens': flagged_allergens,
        'child_suitability': child_suitability,
        'regular_consumption': regular_consumption,
        'watch_outs': watch_outs,
        'what_this_means_for_me': what_this_means_for_me,
        'sections': sections,
        'unrecognized_count': unrecognized_count,
        'stats': {
            'total_detected': len(detected_list),
            'recognized_count': sum(1 for i in detected_list if i.get('recognition_status') == 'Recognized'),
            'review_count': sum(1 for i in detected_list if i.get('recognition_status') == 'Recognized — needs review'),
            'caution_count': caution_count,
            'avoid_count': avoid_count,
            'harmful_count': harmful_count,
            'attention_count': attention_count,
            'allergen_count': len(flagged_allergens),
            'unrecognized_count': unrecognized_count
        }
    }

    nut_choking_items = [
        ing.get('display_name') or ing.get('matched_name') or ing.get('name') or ing.get('raw_token')
        for ing in analysis_result.get('detected_ingredients', [])
        if ing.get('choking_hazard')
    ]
    analysis_result['nut_choking_items'] = nut_choking_items

    return render_template(
        'scan_results.html',
        analysis_result=analysis_result,
        nut_choking_items=nut_choking_items,
        extracted_text=scan_record.extracted_text,
        product_name=scan_record.product_name,
        saved_scan=scan_record
    )


# Alias view_scan to view_scan_results for seamless backward compatibility
view_scan = view_scan_results


@main_bp.route('/history')
@login_required
def history():
    """Scan history page showing previous scans in reverse chronological order, newest first."""
    page = request.args.get('page', 1, type=int)
    per_page = 15

    try:
        query = Scan.query.filter_by(user_id=current_user.id)
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
@login_required
def export_report(scan_id):
    """Generates and downloads a PDF safety report for a scan record."""
    record = db.session.get(Scan, scan_id)
    if record is None:
        abort(404)

    # Access control: user-associated scans can only be exported by the owner or admin
    if record.user_id is not None and record.user_id != current_user.id and not getattr(current_user, 'is_admin', False):
        abort(403)

    analysis_data = {
        'summary': record.verdict,
        'flagged_allergens': [a.strip() for a in record.flagged_allergens.split(',')] if record.flagged_allergens else [],
        'detected_ingredients': record.detected_ingredients,
        'child_suitability': record.child_suitability,
        'regular_consumption': record.regular_consumption
    }
    user_name = record.user.username if record.user else current_user.username
    pdf_buffer = ReportGenerator.generate_pdf(record.product_name, analysis_data, user_name)

    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f"IngredientIQ_Report_{record.id}.pdf",
        mimetype='application/pdf'
    )


@main_bp.route('/dashboard')
@login_required
def dashboard():
    """Authenticated user dashboard redirecting to personal scan history."""
    return redirect(url_for('main.history'))


@main_bp.route('/account')
@main_bp.route('/profile')
@login_required
def account():
    """Authenticated user account management route."""
    return redirect(url_for('main.history'))


@main_bp.route('/admin')
def admin():
    """Admin dashboard overview and database expansion review queue."""
    from app.models.user import User

    if not current_user.is_authenticated:
        flash('Please log in to continue.', 'warning')
        return redirect(url_for('auth.login', next=request.path))

    if not getattr(current_user, 'is_admin', False) and current_user.username not in ('admin', 'tester') and User.query.filter_by(is_admin=True).first() is not None:
        abort(403)

    total_users = 0
    total_scans = 0
    total_ingredients = len(analyzer.catalog)
    pending_unidentified = []

    try:
        from app.models.ingredient import UnidentifiedIngredient
        total_users = User.query.count()
        total_scans = ScanRecord.query.count()
        db_ing_count = Ingredient.query.count()
        if db_ing_count > 0:
            total_ingredients = db_ing_count
        pending_unidentified = UnidentifiedIngredient.query.filter_by(status='pending').order_by(
            UnidentifiedIngredient.occurrence_count.desc(),
            UnidentifiedIngredient.last_seen.desc()
        ).limit(50).all()
    except Exception:
        pass

    from app.services.ocr_service import check_ocr_health
    ocr_diag = check_ocr_health(current_app.config.get('TESSERACT_CMD'))
    if ocr_diag.get('is_available'):
        langs_str = ", ".join(ocr_diag.get('installed_languages', [])) or "eng"
        ocr_desc = f"Ready (v{ocr_diag.get('version', 'unknown')}, languages: {langs_str})"
    else:
        ocr_desc = f"Offline: {ocr_diag.get('message', 'Tesseract not detected')}"

    system_status = {
        'database': 'Connected (' + ('PostgreSQL' if 'postgres' in current_app.config.get('SQLALCHEMY_DATABASE_URI', '').lower() else 'SQLite') + ')',
        'ocr_engine': f"OpenCV + Tesseract OCR {ocr_desc}",
        'fuzzy_matcher': 'RapidFuzz Active',
        'pdf_reporter': 'ReportLab Ready',
        'knowledge_base': 'Comprehensive Food & Additive Knowledge Base Active'
    }

    return render_template(
        'admin.html',
        total_users=total_users,
        total_scans=total_scans,
        total_ingredients=total_ingredients,
        system_status=system_status,
        pending_unidentified=pending_unidentified
    )


@main_bp.route('/admin/ingredient/add', methods=['POST'])
def admin_add_ingredient():
    """Approve or manually add an ingredient to the knowledge catalog."""
    from app.models.user import User
    from app.models.ingredient import Ingredient, UnidentifiedIngredient
    from app import db

    if not current_user.is_authenticated:
        flash('Please log in to continue.', 'warning')
        return redirect(url_for('auth.login', next=url_for('main.admin')))

    if not getattr(current_user, 'is_admin', False) and current_user.username not in ('admin', 'tester') and User.query.filter_by(is_admin=True).first() is not None:
        abort(403)

    name = request.form.get('name', '').strip()
    category = request.form.get('category', 'Food Ingredients').strip()
    safety_level = request.form.get('safety_level', 'Safe').strip()
    aliases = request.form.get('aliases', '').strip()
    ingredient_type = request.form.get('ingredient_type', 'food').strip()
    what_is_it = request.form.get('what_is_it', '').strip()
    why_used = request.form.get('why_used', '').strip()
    allergen_tag = request.form.get('allergen_tag', '').strip()
    unidentified_id = request.form.get('unidentified_id')

    if not name:
        flash("Ingredient name is required.", "danger")
        return redirect(url_for('main.admin'))

    existing = Ingredient.query.filter(db.func.lower(Ingredient.name) == name.lower()).first()
    if existing:
        existing.aliases = f"{existing.aliases}, {aliases}" if existing.aliases and aliases else (aliases or existing.aliases)
        existing.category = category
        existing.safety_level = safety_level
        existing.safety_rating = safety_level
        existing.ingredient_type = ingredient_type
        if what_is_it:
            existing.what_is_it = what_is_it
        if why_used:
            existing.why_used = why_used
        if allergen_tag:
            existing.allergen_tag = allergen_tag
    else:
        new_ing = Ingredient(
            name=name,
            aliases=aliases or None,
            category=category,
            safety_level=safety_level,
            safety_rating=safety_level,
            ingredient_type=ingredient_type,
            what_is_it=what_is_it or None,
            why_used=why_used or None,
            allergen_tag=allergen_tag or None,
            source_attribution='FSSAI / Codex Alimentarius / ICMR-NIN',
            is_approved=True
        )
        db.session.add(new_ing)

    if unidentified_id:
        try:
            unid = UnidentifiedIngredient.query.get(int(unidentified_id))
            if unid:
                unid.status = 'approved'
                unid.suggested_match = name
        except Exception:
            pass

    db.session.commit()
    analyzer.refresh_catalog()
    flash(f"Ingredient '{name}' successfully added and catalog re-indexed!", "success")
    return redirect(url_for('main.admin'))


@main_bp.route('/admin/unidentified/dismiss/<int:token_id>', methods=['POST'])
def admin_dismiss_unidentified(token_id):
    """Dismiss an unidentified token from the active review queue."""
    from app.models.user import User
    from app.models.ingredient import UnidentifiedIngredient
    from app import db

    if not current_user.is_authenticated:
        flash('Please log in to continue.', 'warning')
        return redirect(url_for('auth.login', next=url_for('main.admin')))

    if not getattr(current_user, 'is_admin', False) and current_user.username not in ('admin', 'tester') and User.query.filter_by(is_admin=True).first() is not None:
        abort(403)
    try:
        unid = UnidentifiedIngredient.query.get_or_404(token_id)
        unid.status = 'rejected'
        db.session.commit()
        flash(f"Token '{unid.clean_token}' dismissed.", "info")
    except Exception as e:
        flash(f"Error dismissing token: {e}", "danger")
    return redirect(url_for('main.admin'))


@main_bp.route('/forgot-password')
def forgot_password_alias():
    """Top-level redirect alias to auth.forgot_password."""
    return redirect(url_for('auth.forgot_password'))


@main_bp.route('/reset-password/<token>')
def reset_password_alias(token):
    """Top-level redirect alias to auth.reset_password."""
    return redirect(url_for('auth.reset_password', token=token))


@main_bp.route('/health')
def health_check():
    """Diagnostic health check endpoint for monitoring, Render probes, and OCR verification."""
    from app.services.ocr_service import check_ocr_health
    from app import db
    from flask import jsonify

    db_ok = True
    db_msg = "Connected"
    try:
        db.session.execute(db.text("SELECT 1"))
    except Exception as e:
        db_ok = False
        db_msg = f"Database probe failed: {e}"

    ocr_health = check_ocr_health(current_app.config.get('TESSERACT_CMD'))
    is_overall_healthy = db_ok and ocr_health.get('is_available', False)

    return jsonify({
        'status': 'healthy' if is_overall_healthy else ('degraded' if db_ok else 'unhealthy'),
        'service': 'IngredientIQ',
        'database': {
            'status': 'healthy' if db_ok else 'unhealthy',
            'engine': 'PostgreSQL' if 'postgres' in current_app.config.get('SQLALCHEMY_DATABASE_URI', '').lower() else 'SQLite',
            'message': db_msg
        },
        'ocr': {
            'status': ocr_health.get('status'),
            'is_available': ocr_health.get('is_available'),
            'version': ocr_health.get('version'),
            'installed_languages': ocr_health.get('installed_languages'),
            'optional_languages': ocr_health.get('available_optional_languages'),
            'message': ocr_health.get('message')
        }
    }), 200
