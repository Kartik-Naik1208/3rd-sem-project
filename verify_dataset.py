import csv
import os
import tempfile
from pathlib import Path
from app import create_app, db
from app.models.ingredient import Ingredient
from database import create_tables, load_ingredients_from_csv, init_db

def run_verifications():
    print("=" * 60)
    print("RUNNING COMPLETE INGREDIENTIQ CSV & DATABASE VERIFICATION")
    print("=" * 60)

    # 1. Verify CSV Structure & Rows
    csv_path = Path(__file__).resolve().parent / 'data' / 'ingredients.csv'
    assert csv_path.exists(), f"CSV file not found at {csv_path}"

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)

    expected_columns = ['name', 'aliases', 'e_number', 'category', 'safety_level', 'health_effects', 'banned_status']
    print(f"\n[Check 1 & 2] Column Header & Row Count:")
    print(f" - Header matches expected 7 columns: {header == expected_columns}")
    assert header == expected_columns, f"Header mismatch: {header}"
    print(f" - Exactly 80 data rows: {len(rows) == 80} (Found: {len(rows)})")
    assert len(rows) == 80, f"Expected 80 rows, found {len(rows)}"

    # Check each row has 7 columns
    all_7_cols = all(len(r) == 7 for r in rows)
    print(f" - Every single row has exactly 7 columns: {all_7_cols}")
    assert all_7_cols

    # Check unique names
    names = [r[0].strip() for r in rows]
    assert len(set(names)) == 80, f"Found duplicates in names: {len(set(names))}"
    print(f" - All 80 ingredient names are unique: True")

    # 3. Check Safety Levels
    allowed_safeties = {'Safe', 'Caution', 'Harmful'}
    invalid_safeties = [r[4] for r in rows if r[4] not in allowed_safeties]
    print(f"\n[Check 3] Safety Level Validation:")
    print(f" - All safety levels are valid ('Safe', 'Caution', 'Harmful'): {len(invalid_safeties) == 0}")
    assert len(invalid_safeties) == 0, f"Invalid safety levels: {invalid_safeties}"
    safety_counts = {}
    for r in rows:
        safety_counts[r[4]] = safety_counts.get(r[4], 0) + 1
    print(f" - Distribution: {safety_counts}")

    # 4. Check Banned Status Values
    allowed_banned = {'True', 'False'}
    invalid_banned = [r[6] for r in rows if r[6] not in allowed_banned]
    print(f"\n[Check 4] Banned Status Validation:")
    print(f" - All banned-status values are valid booleans ('True' or 'False'): {len(invalid_banned) == 0}")
    assert len(invalid_banned) == 0, f"Invalid banned values: {invalid_banned}"
    banned_counts = {}
    for r in rows:
        banned_counts[r[6]] = banned_counts.get(r[6], 0) + 1
    print(f" - Distribution: {banned_counts}")

    # 5. Check Fresh Database Loading (in-memory SQLite)
    print(f"\n[Check 5] Fresh Database Loading:")
    fresh_app = create_app('testing')
    with fresh_app.app_context():
        create_tables(fresh_app)
        loaded = load_ingredients_from_csv(csv_path=csv_path, app=fresh_app)
        db_count_fresh = Ingredient.query.count()
        print(f" - Fresh DB records loaded: {loaded}")
        print(f" - Fresh DB total ingredients in database: {db_count_fresh}")
        assert db_count_fresh == 80, f"Expected 80 records in fresh DB, got {db_count_fresh}"

        # 6. Check Idempotence / Second Run Duplicate Check
        print(f"\n[Check 6] Second-Run Duplicate Check (Idempotence):")
        second_loaded = load_ingredients_from_csv(csv_path=csv_path, app=fresh_app)
        db_count_second = Ingredient.query.count()
        print(f" - Second run processed: {second_loaded}")
        print(f" - Count after second run: {db_count_second}")
        assert db_count_second == 80, f"Count increased from 80 to {db_count_second} on second run!"
        print(f" - Verified: Repeated run did NOT increase ingredient count (0 duplicates created).")

        # 7. Check Required Ingredients & Additives Querying
        print(f"\n[Check 7] Querying Required Ingredients & Additives:")
        required_items = [
            ("Sugar", None),
            ("Salt", None),
            ("Wheat flour", None),
            ("Palm oil", None),
            ("Citric acid", "E330"),
            ("Sodium benzoate", "E211"),
            ("Tartrazine", "E102"),
            ("Monosodium glutamate", "E621"),
            ("Aspartame", "E951"),
            ("Caramel colour", "E150"),
            ("Soy lecithin", "E322"),
            ("Gelatin", "E441")
        ]

        for req_name, expected_e in required_items:
            item = Ingredient.query.filter_by(name=req_name).first()
            assert item is not None, f"Could not find required ingredient '{req_name}'"
            if expected_e:
                assert item.e_number == expected_e, f"{req_name}: expected E-number {expected_e}, got {item.e_number}"
            print(f" - Found '{item.name}' | E-Number: {item.e_number or 'N/A'} | Category: {item.category} | Safety: {item.safety_level} | Banned: {item.banned_status}")

        # Also verify sample prompt items
        extra_prompt_items = ["Milk powder", "Cornstarch", "Glucose syrup", "Vinegar", "Baking soda"]
        for extra in extra_prompt_items:
            item = Ingredient.query.filter_by(name=extra).first()
            assert item is not None, f"Could not find prompt ingredient '{extra}'"
            print(f" - Found '{item.name}' | Category: {item.category} | Safety: {item.safety_level}")

    print("\n" + "=" * 60)
    print("ALL 7 VERIFICATION CHECKS PASSED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == '__main__':
    run_verifications()
