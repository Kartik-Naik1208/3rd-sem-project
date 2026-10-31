import unittest
from app import create_app, db
from app.models.user import User
from app.models.ingredient import Ingredient, UnidentifiedIngredient
from app.services.analyzer_service import IngredientAnalyzer, is_ocr_artifact, normalize_inverted_phrase, extract_percentage
from database import load_all_ingredients, load_ingredients_from_csv, load_food_ingredients_from_csv


class TestFoodIngredientRecognition(unittest.TestCase):
    """
    Comprehensive test suite verifying food ingredient recognition, database expansion,
    multi-alias matching, plain-English explanations, and classification accuracy.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = create_app('testing')
        with cls.app.app_context():
            db.create_all()
            load_all_ingredients(cls.app)

    def setUp(self):
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.client = self.app.test_client()
        self.analyzer = IngredientAnalyzer()

    def tearDown(self):
        self.app_context.pop()

    def login(self, username='tester', password='password123'):
        user = User.query.filter_by(username=username).first()
        if not user:
            user = User(username=username, email=f"{username}@example.com")
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
        return self.client.post('/auth/login', data={'username': username, 'password': password}, follow_redirects=True)

    def test_01_all_33_required_ingredients_recognized(self):
        """Criterion 1: Every one of the 33 specified ingredients matches with high confidence."""
        required_33 = [
            "Peanut", "Groundnut", "Cashew", "Almond", "Potato", "Rice", "Rice flakes",
            "Poha", "Wheat flour", "Maida", "Besan", "Chickpeas", "Palm oil", "Palmolein",
            "Sunflower oil", "Coconut oil", "Turmeric", "Haldi", "Cumin", "Jeera",
            "Coriander", "Dhania", "Sugar", "Salt", "Milk powder", "Whey", "Cocoa powder",
            "Citric acid", "Sodium benzoate", "Maltodextrin", "Lecithin", "Xanthan gum", "Pectin"
        ]

        for item_name in required_33:
            item, conf, status = self.analyzer.match_ingredient_detailed(item_name)
            self.assertIsNotNone(item, f"Failed to match required ingredient: '{item_name}'")
            self.assertGreaterEqual(conf, 85.0, f"Confidence too low for '{item_name}': {conf}")
            self.assertEqual(status, 'Recognized', f"Status not 'Recognized' for '{item_name}': {status}")

    def test_02_staple_foods_not_marked_as_unverified_or_harmful(self):
        """Criterion 2: Wholesome foods (peanuts, cashews, potatoes) have Safe rating, not Unknown/Harmful."""
        staples = ["Peanut", "Cashew", "Potato", "Rice", "Turmeric", "Besan"]
        for s in staples:
            item, conf, status = self.analyzer.match_ingredient_detailed(s)
            self.assertEqual(item['safety_level'], 'Safe', f"Staple food '{s}' had unsafe level: {item['safety_level']}")
            details = self.analyzer.analyze(s)
            detected = details['detected_ingredients'][0]
            self.assertFalse(detected['is_unrecognized'], f"Staple '{s}' was flagged as unrecognized")
            self.assertEqual(detected['simple_status'], 'No specific concern identified')

    def test_03_allergen_warnings_separate_from_safety_rating(self):
        """Criterion 3: Peanuts and milk powder are Safe food ingredients with distinct allergen tags."""
        peanut_match, _, _ = self.analyzer.match_ingredient_detailed("Peanut")
        self.assertEqual(peanut_match['safety_level'], 'Safe')
        self.assertIn('peanut', peanut_match.get('allergen_tag', '').lower())

        milk_match, _, _ = self.analyzer.match_ingredient_detailed("Milk powder")
        self.assertEqual(milk_match['safety_level'], 'Safe')
        self.assertIn('milk', milk_match.get('allergen_tag', '').lower())

        # Analysis without allergy
        res_normal = self.analyzer.analyze("Peanut, Milk powder")
        self.assertEqual(res_normal['base_verdict'], 'Clean & Safe')

        # Analysis with peanut allergy triggers personal conflict override to Avoid
        res_allergic = self.analyzer.analyze("Peanut, Milk powder", user_allergies=['peanut'])
        self.assertEqual(res_allergic['summary'], 'Avoid')
        self.assertTrue(res_allergic['has_conflict'])

    def test_04_plain_english_explanations_populated(self):
        """Criterion 4: Ingredients include rich what_is_it, why_used, child_considerations, and regular_consumption."""
        res = self.analyzer.analyze("Potato, Turmeric, Salt")
        for ing in res['detected_ingredients']:
            self.assertTrue(len(ing.get('what_it_does', '')) > 5)
            self.assertTrue(len(ing.get('simple_explanation', '')) > 5)
            self.assertTrue(len(ing.get('child_concerns', '')) > 5)
            self.assertTrue(len(ing.get('regular_consumption_note', '')) > 5)

    def test_05_indian_culinary_terms_mapped_to_canonical(self):
        """Criterion 5: Hindi / Indian names map to canonical entries."""
        mappings = [
            ("Haldi", "Turmeric"),
            ("Jeera", "Cumin"),
            ("Dhania", "Coriander"),
            ("Poha", "Flattened rice"),
            ("Besan", "Chickpea flour"),
            ("Maida", "Refined wheat flour"),
            ("Aloo", "Potato"),
            ("Moongphali", "Peanut"),
        ]
        for hindi, canonical in mappings:
            item, conf, status = self.analyzer.match_ingredient_detailed(hindi)
            self.assertIsNotNone(item, f"Failed to match Indian term '{hindi}'")
            self.assertEqual(item['name'].lower(), canonical.lower(), f"'{hindi}' mapped to '{item['name']}', expected '{canonical}'")
            self.assertEqual(status, 'Recognized')

    def test_06_botanical_and_multi_alias_recognition(self):
        """Criterion 6: Scientific/botanical and alternative industry aliases match accurately."""
        scientific_items = [
            ("Arachis hypogaea", "Peanut"),
            ("Curcuma longa", "Turmeric"),
            ("Solanum tuberosum", "Potato"),
            ("Palmolein", "Palm olein oil"),
            ("Groundnut", "Peanut"),
        ]
        for query, expected_canonical in scientific_items:
            item, conf, _ = self.analyzer.match_ingredient_detailed(query)
            self.assertIsNotNone(item, f"Failed scientific alias: '{query}'")
            self.assertEqual(item['name'].lower(), expected_canonical.lower())

    def test_07_ins_and_e_number_recognition(self):
        """Criterion 7: INS and E-numbers are recognized identically."""
        ins_tests = [
            ("INS 330", "Citric acid"),
            ("INS 211", "Sodium benzoate"),
            ("E330", "Citric acid"),
            ("E211", "Sodium benzoate"),
            ("E621", "Monosodium glutamate"),
        ]
        for code, expected_name in ins_tests:
            item, conf, status = self.analyzer.match_ingredient_detailed(code)
            self.assertIsNotNone(item, f"Failed INS/E-number match for '{code}'")
            self.assertEqual(item['name'].lower(), expected_name.lower())
            self.assertEqual(status, 'Recognized')

    def test_08_context_aware_inverted_phrase_matching(self):
        """Criterion 8: Phrases like 'Flour (Wheat)' or 'Oil (Palmolein)' are inverted and recognized."""
        self.assertEqual(normalize_inverted_phrase("Flour (Wheat)"), "Wheat Flour")
        self.assertEqual(normalize_inverted_phrase("Oil (Palmolein)"), "Palmolein Oil")

        item1, conf1, status1 = self.analyzer.match_ingredient_detailed("Flour (Wheat)")
        self.assertIsNotNone(item1)
        self.assertEqual(status1, 'Recognized')

        item2, conf2, status2 = self.analyzer.match_ingredient_detailed("Oil (Palmolein)")
        self.assertIsNotNone(item2)
        self.assertEqual(status2, 'Recognized')

    def test_09_compound_parentheses_token_parsing(self):
        """Criterion 9: Tokenizer preserves nested parentheses without splitting sub-ingredients incorrectly."""
        raw = "Potato flakes (Potato (60%), Salt), Palmolein Oil, Peanuts (10%), Salt"
        tokens = self.analyzer.parse_tokens(raw)
        self.assertIn("Potato flakes (Potato (60%), Salt)", tokens)
        self.assertIn("Palmolein Oil", tokens)
        self.assertIn("Peanuts (10%)", tokens)
        self.assertIn("Salt", tokens)

    def test_10_percentage_extraction(self):
        """Criterion 10: Percentage values like (60%) or 10% are extracted and clean tokens preserved."""
        clean1, pct1 = extract_percentage("Potato (60%)")
        self.assertEqual(clean1, "Potato")
        self.assertEqual(pct1, "60%")

        clean2, pct2 = extract_percentage("Peanuts (10%)")
        self.assertEqual(clean2, "Peanuts")
        self.assertEqual(pct2, "10%")

        res = self.analyzer.analyze("Potato (60%), Peanuts (10%)")
        detected = res['detected_ingredients']
        self.assertEqual(detected[0]['percentage'], "60%")
        self.assertEqual(detected[1]['percentage'], "10%")

    def test_11_label_noise_filtering(self):
        """Criterion 11: Non-ingredient noise (Batch numbers, Net weights, Mfg dates) is stripped."""
        raw = "Ingredients: Potato, Salt, Turmeric. Batch No: B-9281, Net Wt: 200g, Mfg Date: 2026-10-12"
        tokens = self.analyzer.parse_tokens(raw)
        self.assertNotIn("Batch No: B-9281", tokens)
        self.assertNotIn("Net Wt: 200g", tokens)
        self.assertNotIn("Mfg Date: 2026-10-12", tokens)
        self.assertIn("Potato", tokens)

    def test_12_food_vs_additive_classification(self):
        """Criterion 12: Ordinary foods carry ingredient_type='food', chemical additives carry 'additive'."""
        food_item, _, _ = self.analyzer.match_ingredient_detailed("Peanut")
        self.assertEqual(food_item.get('ingredient_type'), 'food')

        flour_item, _, _ = self.analyzer.match_ingredient_detailed("Wheat flour")
        self.assertEqual(flour_item.get('ingredient_type'), 'food')

        additive_item, _, _ = self.analyzer.match_ingredient_detailed("Sodium benzoate")
        self.assertEqual(additive_item.get('ingredient_type'), 'additive')

    def test_13_conservative_ocr_typo_correction(self):
        """Criterion 13: Common OCR typos on labels are corrected to their intended ingredients."""
        typos = [
            ("Peanul", "Peanut"),
            ("Tumeric", "Turmeric"),
            ("Palmolien", "Palm olein oil"),
            ("Potatos", "Potato"),
        ]
        for typo, expected in typos:
            item, conf, status = self.analyzer.match_ingredient_detailed(typo)
            self.assertIsNotNone(item, f"Failed typo match for '{typo}'")
            self.assertEqual(item['name'].lower(), expected.lower())
            self.assertEqual(status, 'Recognized')

    def test_14_recognition_statuses_and_ocr_artifact_detection(self):
        """Criterion 14: Four recognition statuses are properly identified."""
        # 1. Recognized
        _, _, s_rec = self.analyzer.match_ingredient_detailed("Almond")
        self.assertEqual(s_rec, 'Recognized')

        # 2. OCR issue
        self.assertTrue(is_ocr_artifact("x#29-a"))
        self.assertTrue(is_ocr_artifact("@#$%^"))
        _, _, s_ocr = self.analyzer.match_ingredient_detailed("x#29-a")
        self.assertEqual(s_ocr, 'OCR issue')

        # 3. Unidentified (real word, but not in DB)
        _, _, s_unid = self.analyzer.match_ingredient_detailed("Moringa oleifera leaves")
        self.assertEqual(s_unid, 'Unidentified')

    def test_15_unidentified_tokens_logged_in_database(self):
        """Criterion 15: Scanning unidentified tokens logs them in UnidentifiedIngredient table for review."""
        token_name = "Moringa leaf extract"
        res = self.analyzer.analyze(token_name)
        self.assertEqual(res['unrecognized_count'], 1)

        logged = UnidentifiedIngredient.query.filter_by(clean_token=token_name).first()
        self.assertIsNotNone(logged, "Unidentified ingredient was not logged in database")
        self.assertEqual(logged.status, 'pending')
        self.assertGreaterEqual(logged.occurrence_count, 1)

    def test_16_admin_review_and_approval_flow(self):
        """Criterion 16: Admin interface can approve and add new ingredient dynamically."""
        self.login()
        # Post to /admin/ingredient/add
        resp = self.client.post('/admin/ingredient/add', data={
            'name': 'Moringa Oleifera',
            'category': 'Food Ingredients',
            'ingredient_type': 'food',
            'safety_level': 'Safe',
            'aliases': 'Moringa, Drumstick leaf powder',
            'what_is_it': 'Nutrient-rich leaves of the drumstick tree.',
            'why_used': 'Nutritional fortification and natural greens.',
            'allergen_tag': ''
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        # Check ingredient is now in DB
        added = Ingredient.query.filter_by(name='Moringa Oleifera').first()
        self.assertIsNotNone(added)

        # Analyzer immediately recognizes it
        item, conf, status = self.analyzer.match_ingredient_detailed("Drumstick leaf powder")
        self.assertIsNotNone(item)
        self.assertEqual(item['name'], 'Moringa Oleifera')
        self.assertEqual(status, 'Recognized')


if __name__ == '__main__':
    unittest.main()
