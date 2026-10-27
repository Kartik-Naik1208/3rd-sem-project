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

    # Additional metadata to support full result viewing and PDF export
    product_name = db.Column(db.String(150), nullable=False, default='Scanned Product')
    detected_ingredients_json = db.Column(db.Text, nullable=True)
    flagged_allergens = db.Column(db.String(255), nullable=True)
    personal_conflicts_json = db.Column(db.Text, nullable=True)
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
