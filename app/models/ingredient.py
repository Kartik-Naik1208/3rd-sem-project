from datetime import datetime, timezone
import json
from app import db


class Ingredient(db.Model):
    """Catalog of known food and cosmetic ingredients with safety details."""
    __tablename__ = 'ingredients'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False, index=True)
    aliases = db.Column(db.String(255), nullable=True)
    e_number = db.Column(db.String(20), index=True, nullable=True)
    category = db.Column(db.String(80), nullable=False, default='General')
    safety_level = db.Column(db.String(30), nullable=False, default='Safe')  # Safe, Caution, Harmful
    safety_rating = db.Column(db.String(30), nullable=False, default='Safe')  # Maintained for UI compatibility
    health_effects = db.Column(db.Text, nullable=True)
    banned_status = db.Column(db.Boolean, default=False, nullable=False)
    allergen_type = db.Column(db.String(100), nullable=True)  # Gluten, Dairy, Soy, Nuts, Sulfites, etc.
    allergen_tag = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)
    diet_flags = db.Column(db.String(255), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    # Expanded food ingredient fields
    ingredient_type = db.Column(db.String(50), nullable=False, default='food')  # food, additive, processing_aid
    what_is_it = db.Column(db.Text, nullable=True)
    why_used = db.Column(db.Text, nullable=True)
    common_uses = db.Column(db.Text, nullable=True)
    child_considerations = db.Column(db.Text, nullable=True)
    regular_consumption = db.Column(db.Text, nullable=True)
    source_attribution = db.Column(db.String(255), nullable=True, default='FSSAI / Codex Alimentarius / ICMR-NIN')
    is_approved = db.Column(db.Boolean, default=True, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'aliases': self.aliases,
            'e_number': self.e_number,
            'category': self.category,
            'safety_level': self.safety_level,
            'safety_rating': self.safety_rating,
            'banned_status': self.banned_status,
            'allergen_type': self.allergen_type,
            'allergen_tag': self.allergen_tag,
            'description': self.description,
            'health_effects': self.health_effects,
            'diet_flags': self.diet_flags,
            'notes': self.notes,
            'ingredient_type': self.ingredient_type,
            'what_is_it': self.what_is_it,
            'why_used': self.why_used,
            'common_uses': self.common_uses,
            'child_considerations': self.child_considerations,
            'regular_consumption': self.regular_consumption,
            'source_attribution': self.source_attribution,
            'is_approved': self.is_approved,
        }

    def __repr__(self):
        return f'<Ingredient {self.name} [{self.safety_level}]>'


class Scan(db.Model):
    """History log of user image/text scans and analysis results."""
    __tablename__ = 'scans'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    image_filename = db.Column(db.String(255), nullable=True)
    extracted_text = db.Column(db.Text, nullable=True)
    score = db.Column(db.Integer, nullable=False, default=100)
    verdict = db.Column(db.String(50), nullable=False, default='Clean & Safe')
    scan_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Additional metadata to support full result viewing, child/regular assessments, and PDF export
    product_name = db.Column(db.String(150), nullable=False, default='Scanned Product')
    detected_ingredients_json = db.Column(db.Text, nullable=True)
    flagged_allergens = db.Column(db.String(255), nullable=True)
    personal_conflicts_json = db.Column(db.Text, nullable=True)
    child_suitability_json = db.Column(db.Text, nullable=True)
    regular_consumption_json = db.Column(db.Text, nullable=True)
    sections_json = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    @property
    def detected_ingredients(self):
        if self.detected_ingredients_json:
            try:
                return json.loads(self.detected_ingredients_json)
            except Exception:
                return []
        return []

    @detected_ingredients.setter
    def detected_ingredients(self, value):
        self.detected_ingredients_json = json.dumps(value)

    @property
    def personal_conflicts(self):
        if self.personal_conflicts_json:
            try:
                return json.loads(self.personal_conflicts_json)
            except Exception:
                return []
        return []

    @personal_conflicts.setter
    def personal_conflicts(self, value):
        self.personal_conflicts_json = json.dumps(value)

    @property
    def child_suitability(self):
        if self.child_suitability_json:
            try:
                return json.loads(self.child_suitability_json)
            except Exception:
                return {}
        return {}

    @child_suitability.setter
    def child_suitability(self, value):
        self.child_suitability_json = json.dumps(value)

    @property
    def regular_consumption(self):
        if self.regular_consumption_json:
            try:
                return json.loads(self.regular_consumption_json)
            except Exception:
                return {}
        return {}

    @regular_consumption.setter
    def regular_consumption(self, value):
        self.regular_consumption_json = json.dumps(value)

    @property
    def detected_sections(self):
        if self.sections_json:
            try:
                return json.loads(self.sections_json)
            except Exception:
                return {}
        return {}

    @detected_sections.setter
    def detected_sections(self, value):
        self.sections_json = json.dumps(value)

    @property
    def unrecognized_count(self):
        return sum(1 for i in self.detected_ingredients if i.get('is_unrecognized'))

    # Backwards compatibility properties
    @property
    def created_at(self):
        return self.scan_date

    @created_at.setter
    def created_at(self, value):
        self.scan_date = value

    @property
    def safety_summary(self):
        return self.verdict

    @safety_summary.setter
    def safety_summary(self, value):
        self.verdict = value

    def __repr__(self):
        return f'<Scan #{self.id} [{self.verdict} - Score: {self.score}]>'


# Maintain ScanRecord as alias for backward compatibility
ScanRecord = Scan


class UnidentifiedIngredient(db.Model):
    """Log of unrecognized or review-needed tokens captured during scans for database expansion."""
    __tablename__ = 'unidentified_ingredients'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    raw_token = db.Column(db.String(255), nullable=False)
    clean_token = db.Column(db.String(255), nullable=False, index=True)
    confidence = db.Column(db.Integer, nullable=False, default=0)
    suggested_match = db.Column(db.String(150), nullable=True)
    scan_id = db.Column(db.Integer, db.ForeignKey('scans.id'), nullable=True)
    occurrence_count = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(db.String(50), nullable=False, default='pending')  # pending, approved, rejected
    first_seen = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    last_seen = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'raw_token': self.raw_token,
            'clean_token': self.clean_token,
            'confidence': self.confidence,
            'suggested_match': self.suggested_match,
            'scan_id': self.scan_id,
            'occurrence_count': self.occurrence_count,
            'status': self.status,
            'first_seen': self.first_seen.isoformat() if self.first_seen else None,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None,
        }

    def __repr__(self):
        return f'<UnidentifiedIngredient {self.clean_token} ({self.occurrence_count}x)>'

