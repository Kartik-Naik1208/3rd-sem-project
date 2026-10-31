import csv
import os
from pathlib import Path
from flask import current_app
from sqlalchemy import text, inspect
from app import create_app, db
from app.models.ingredient import Ingredient

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CSV_PATH = BASE_DIR / 'data' / 'ingredients.csv'
DEFAULT_FOOD_CSV_PATH = BASE_DIR / 'data' / 'food_ingredients.csv'

REQUIRED_COLUMNS = [
    'name',
    'aliases',
    'e_number',
    'category',
    'safety_level',
    'health_effects',
    'banned_status',
    'allergen_tag',
    'diet_flags'
]

FOOD_REQUIRED_COLUMNS = [
    'name',
    'aliases',
    'e_number',
    'category',
    'safety_level',
    'health_effects',
    'banned_status',
    'allergen_tag',
    'diet_flags',
    'ingredient_type',
    'what_is_it',
    'why_used',
    'common_uses',
    'child_considerations',
    'regular_consumption',
    'source_attribution'
]

ALLOWED_SAFETY_LEVELS = {'Safe', 'Caution', 'Harmful'}


def get_app(app=None):
    """Returns an active Flask application instance."""
    if app is not None:
        return app
    if current_app:
        return current_app._get_current_object()
    return create_app()


def create_tables(app=None):
    """
    Creates all missing database tables and applies non-destructive schema migrations
    to support new Ingredient columns without deleting or recreating the database.
    """
    application = get_app(app)
    with application.app_context():
        # 1. Create any missing tables defined in models
        db.create_all()

        # 2. Check and migrate SQLite columns if ingredients table already existed
        inspector = inspect(db.engine)
        if 'ingredients' in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns('ingredients')]
            
            # Non-destructive migrations for new columns
            alter_statements = []
            if 'aliases' not in columns:
                alter_statements.append("ALTER TABLE ingredients ADD COLUMN aliases VARCHAR(255)")
            if 'safety_level' not in columns:
                alter_statements.append("ALTER TABLE ingredients ADD COLUMN safety_level VARCHAR(30) DEFAULT 'Safe'")
            if 'banned_status' not in columns:
                alter_statements.append("ALTER TABLE ingredients ADD COLUMN banned_status BOOLEAN DEFAULT 0 NOT NULL")
            if 'allergen_tag' not in columns:
                alter_statements.append("ALTER TABLE ingredients ADD COLUMN allergen_tag VARCHAR(255)")
            if 'diet_flags' not in columns:
                alter_statements.append("ALTER TABLE ingredients ADD COLUMN diet_flags VARCHAR(255)")
            if 'notes' not in columns:
                alter_statements.append("ALTER TABLE ingredients ADD COLUMN notes TEXT")
            if 'ingredient_type' not in columns:
                alter_statements.append("ALTER TABLE ingredients ADD COLUMN ingredient_type VARCHAR(50) DEFAULT 'food'")
            if 'what_is_it' not in columns:
                alter_statements.append("ALTER TABLE ingredients ADD COLUMN what_is_it TEXT")
            if 'why_used' not in columns:
                alter_statements.append("ALTER TABLE ingredients ADD COLUMN why_used TEXT")
            if 'common_uses' not in columns:
                alter_statements.append("ALTER TABLE ingredients ADD COLUMN common_uses TEXT")
            if 'child_considerations' not in columns:
                alter_statements.append("ALTER TABLE ingredients ADD COLUMN child_considerations TEXT")
            if 'regular_consumption' not in columns:
                alter_statements.append("ALTER TABLE ingredients ADD COLUMN regular_consumption TEXT")
            if 'source_attribution' not in columns:
                alter_statements.append("ALTER TABLE ingredients ADD COLUMN source_attribution VARCHAR(255) DEFAULT 'FSSAI / Codex Alimentarius / ICMR-NIN'")
            if 'is_approved' not in columns:
                alter_statements.append("ALTER TABLE ingredients ADD COLUMN is_approved BOOLEAN DEFAULT 1 NOT NULL")

            for stmt in alter_statements:
                with db.engine.connect() as conn:
                    conn.execute(text(stmt))
                    conn.commit()

        # 3. Check and migrate SQLite columns if scans table already existed
        if 'scans' in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns('scans')]
            alter_scans = []
            if 'score' not in columns:
                alter_scans.append("ALTER TABLE scans ADD COLUMN score INTEGER DEFAULT 100")
            if 'verdict' not in columns:
                alter_scans.append("ALTER TABLE scans ADD COLUMN verdict VARCHAR(50) DEFAULT 'Clean & Safe'")
            if 'scan_date' not in columns:
                alter_scans.append("ALTER TABLE scans ADD COLUMN scan_date DATETIME")
            if 'product_name' not in columns:
                alter_scans.append("ALTER TABLE scans ADD COLUMN product_name VARCHAR(150) DEFAULT 'Scanned Product'")
            if 'personal_conflicts_json' not in columns:
                alter_scans.append("ALTER TABLE scans ADD COLUMN personal_conflicts_json TEXT")
            if 'child_suitability_json' not in columns:
                alter_scans.append("ALTER TABLE scans ADD COLUMN child_suitability_json TEXT")
            if 'regular_consumption_json' not in columns:
                alter_scans.append("ALTER TABLE scans ADD COLUMN regular_consumption_json TEXT")
            if 'sections_json' not in columns:
                alter_scans.append("ALTER TABLE scans ADD COLUMN sections_json TEXT")

            for stmt in alter_scans:
                with db.engine.connect() as conn:
                    conn.execute(text(stmt))
                    conn.commit()


def parse_boolean(val):
    """Converts boolean string representation into Python bool."""
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in ('true', '1', 't', 'yes', 'y'):
        return True
    if s in ('false', '0', 'f', 'no', 'n'):
        return False
    raise ValueError(f"Invalid boolean value for banned_status: '{val}'. Expected 'True' or 'False'.")


def load_ingredients_from_csv(csv_path=None, app=None):
    """
    Reads data/ingredients.csv, validates columns & values, maps to Ingredient model,
    upserts by normalized ingredient name, commits or rolls back, and closes session.
    """
    if csv_path is None:
        target_path = DEFAULT_CSV_PATH
    else:
        target_path = Path(csv_path)
        if not target_path.is_absolute():
            target_path = BASE_DIR / target_path

    if not target_path.exists():
        raise FileNotFoundError(f"Ingredients CSV file not found at: {target_path}")

    application = get_app(app)

    with application.app_context():
        processed_count = 0
        try:
            with open(target_path, mode='r', encoding='utf-8') as f:
                reader = csv.reader(f)
                try:
                    header = next(reader)
                except StopIteration:
                    raise ValueError(f"CSV file '{target_path}' is empty.")

                cleaned_header = [col.strip().lstrip('\ufeff') for col in header]
                if cleaned_header != REQUIRED_COLUMNS:
                    raise ValueError(
                        f"CSV header mismatch in '{target_path}'.\n"
                        f"Expected: {REQUIRED_COLUMNS}\n"
                        f"Received: {cleaned_header}"
                    )

                for row_idx, row in enumerate(reader, start=2):
                    if not row or all(c.strip() == '' for c in row):
                        continue  # Skip blank lines

                    if len(row) != len(REQUIRED_COLUMNS):
                        raise ValueError(
                            f"Row {row_idx} has {len(row)} columns, expected {len(REQUIRED_COLUMNS)}."
                        )

                    row_dict = dict(zip(cleaned_header, [c.strip() for c in row]))

                    name = row_dict['name']
                    if not name:
                        raise ValueError(f"Row {row_idx} is missing a required 'name'.")

                    safety_level = row_dict['safety_level']
                    if safety_level not in ALLOWED_SAFETY_LEVELS:
                        raise ValueError(
                            f"Row {row_idx} ('{name}'): Invalid safety_level '{safety_level}'. "
                            f"Must be one of {sorted(list(ALLOWED_SAFETY_LEVELS))}."
                        )

                    banned_bool = parse_boolean(row_dict['banned_status'])
                    e_number = row_dict['e_number'] or None
                    aliases = row_dict['aliases'] or None
                    category = row_dict['category'] or 'General'
                    health_effects = row_dict['health_effects'] or None
                    allergen_tag = row_dict.get('allergen_tag') or None
                    diet_flags = row_dict.get('diet_flags') or None

                    # Query by normalized unique key
                    existing = Ingredient.query.filter(
                        db.func.lower(Ingredient.name) == name.lower()
                    ).first()

                    if existing:
                        # Update existing record
                        existing.name = name
                        existing.aliases = aliases
                        existing.e_number = e_number
                        existing.category = category
                        existing.safety_level = safety_level
                        existing.safety_rating = safety_level
                        existing.health_effects = health_effects
                        existing.banned_status = banned_bool
                        existing.allergen_tag = allergen_tag
                        existing.diet_flags = diet_flags
                        # Handle absent model fields
                        if not hasattr(existing, 'notes') or existing.notes is None:
                            existing.notes = None
                    else:
                        # Insert new record
                        new_ingredient = Ingredient(
                            name=name,
                            aliases=aliases,
                            e_number=e_number,
                            category=category,
                            safety_level=safety_level,
                            safety_rating=safety_level,
                            health_effects=health_effects,
                            banned_status=banned_bool,
                            allergen_tag=allergen_tag,
                            allergen_type=None,
                            description=None,
                            diet_flags=diet_flags,
                            notes=None
                        )
                        db.session.add(new_ingredient)

                    processed_count += 1

            # Commit transaction on success
            db.session.commit()
            return processed_count

        except Exception:
            db.session.rollback()
            raise
        finally:
            db.session.remove()


def load_food_ingredients_from_csv(csv_path=None, app=None):
    """
    Reads data/food_ingredients.csv, validates columns & values, maps to Ingredient model,
    upserts by normalized ingredient name, commits or rolls back, and closes session.
    """
    if csv_path is None:
        target_path = DEFAULT_FOOD_CSV_PATH
    else:
        target_path = Path(csv_path)
        if not target_path.is_absolute():
            target_path = BASE_DIR / target_path

    if not target_path.exists():
        return 0

    application = get_app(app)

    with application.app_context():
        processed_count = 0
        try:
            with open(target_path, mode='r', encoding='utf-8') as f:
                reader = csv.reader(f)
                try:
                    header = next(reader)
                except StopIteration:
                    return 0

                cleaned_header = [col.strip().lstrip('\ufeff') for col in header]
                for row_idx, row in enumerate(reader, start=2):
                    if not row or all(c.strip() == '' for c in row):
                        continue

                    if len(row) != len(cleaned_header):
                        continue

                    row_dict = dict(zip(cleaned_header, [c.strip() for c in row]))
                    name = row_dict.get('name')
                    if not name:
                        continue

                    safety_level = row_dict.get('safety_level', 'Safe')
                    if safety_level not in ALLOWED_SAFETY_LEVELS:
                        safety_level = 'Safe'

                    banned_bool = parse_boolean(row_dict.get('banned_status', 'False'))
                    e_number = row_dict.get('e_number') or None
                    aliases = row_dict.get('aliases') or None
                    category = row_dict.get('category') or 'Food Ingredients'
                    health_effects = row_dict.get('health_effects') or None
                    allergen_tag = row_dict.get('allergen_tag') or None
                    diet_flags = row_dict.get('diet_flags') or None
                    ingredient_type = row_dict.get('ingredient_type') or 'food'
                    what_is_it = row_dict.get('what_is_it') or None
                    why_used = row_dict.get('why_used') or None
                    common_uses = row_dict.get('common_uses') or None
                    child_considerations = row_dict.get('child_considerations') or None
                    regular_consumption = row_dict.get('regular_consumption') or None
                    source_attribution = row_dict.get('source_attribution') or 'FSSAI / Codex Alimentarius / ICMR-NIN'

                    existing = Ingredient.query.filter(
                        db.func.lower(Ingredient.name) == name.lower()
                    ).first()

                    if existing:
                        existing.name = name
                        if aliases:
                            if existing.aliases and aliases not in existing.aliases:
                                existing.aliases = f"{existing.aliases}, {aliases}"
                            else:
                                existing.aliases = aliases
                        if e_number:
                            existing.e_number = e_number
                        existing.category = category
                        existing.safety_level = safety_level
                        existing.safety_rating = safety_level
                        existing.health_effects = health_effects or existing.health_effects
                        existing.banned_status = banned_bool
                        existing.allergen_tag = allergen_tag or existing.allergen_tag
                        existing.diet_flags = diet_flags or existing.diet_flags
                        existing.ingredient_type = ingredient_type
                        existing.what_is_it = what_is_it or existing.what_is_it
                        existing.why_used = why_used or existing.why_used
                        existing.common_uses = common_uses or existing.common_uses
                        existing.child_considerations = child_considerations or existing.child_considerations
                        existing.regular_consumption = regular_consumption or existing.regular_consumption
                        existing.source_attribution = source_attribution or existing.source_attribution
                        existing.is_approved = True
                    else:
                        new_ingredient = Ingredient(
                            name=name,
                            aliases=aliases,
                            e_number=e_number,
                            category=category,
                            safety_level=safety_level,
                            safety_rating=safety_level,
                            health_effects=health_effects,
                            banned_status=banned_bool,
                            allergen_tag=allergen_tag,
                            allergen_type=None,
                            description=None,
                            diet_flags=diet_flags,
                            notes=None,
                            ingredient_type=ingredient_type,
                            what_is_it=what_is_it,
                            why_used=why_used,
                            common_uses=common_uses,
                            child_considerations=child_considerations,
                            regular_consumption=regular_consumption,
                            source_attribution=source_attribution,
                            is_approved=True
                        )
                        db.session.add(new_ingredient)

                    processed_count += 1

            db.session.commit()
            return processed_count
        except Exception:
            db.session.rollback()
            raise
        finally:
            db.session.remove()


def load_all_ingredients(app=None):
    """
    Loads base ingredients from data/ingredients.csv and expanded food ingredients
    from data/food_ingredients.csv into the database.
    """
    c1 = load_ingredients_from_csv(app=app)
    c2 = 0
    if DEFAULT_FOOD_CSV_PATH.exists():
        c2 = load_food_ingredients_from_csv(app=app)
    return c1 + c2


def init_db(app=None, csv_path=None):
    """
    Initializes database tables, loads ingredients from CSV, queries counts,
    and prints verification message.
    """
    application = get_app(app)
    with application.app_context():
        # Step 1: Create all missing tables using create_tables()
        create_tables(application)

        # Step 2: Load or update ingredients
        if csv_path:
            processed_count = load_ingredients_from_csv(csv_path=csv_path, app=application)
        else:
            processed_count = load_all_ingredients(app=application)

        # Step 3: Query the database to count the ingredient records
        total_count = Ingredient.query.count()

        # Step 4: Print clear verification message showing CSV records and total stored
        print(
            f"Database initialization complete: Processed {processed_count} CSV records. "
            f"Total ingredients stored in database: {total_count}."
        )
        return total_count


if __name__ == '__main__':
    init_db()
