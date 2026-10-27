import unittest
from app.services.analyzer_service import IngredientAnalyzer, clean_text, SAFETY_SCORE_WEIGHTS


class TestTextCleaning(unittest.TestCase):
    """Test ingredient text cleaning and normalization."""

    def setUp(self):
        self.analyzer = IngredientAnalyzer()

    def test_clean_text_normalizes_extra_whitespace(self):
        raw = "   Wheat   Flour,   Sugar,   Citric   Acid   "
        expected = "Wheat Flour, Sugar, Citric Acid"
        self.assertEqual(clean_text(raw), expected)
        self.assertEqual(self.analyzer.clean_text(raw), expected)

    def test_clean_text_handles_empty_and_whitespace_only(self):
        self.assertEqual(clean_text(""), "")
        self.assertEqual(clean_text("    "), "")
        self.assertEqual(clean_text("\n\t  \r"), "")

    def test_clean_text_handles_none_safely(self):
        self.assertEqual(clean_text(None), "")
        self.assertEqual(self.analyzer.clean_text(None), "")

    def test_clean_text_normalizes_line_breaks(self):
        raw = "Wheat Flour,\r\nSugar,\n\nE621\nSoy Lecithin"
        cleaned = clean_text(raw)
        self.assertNotIn("\n", cleaned)
        self.assertNotIn("\r", cleaned)
        self.assertIn("Wheat Flour", cleaned)
        self.assertIn("Sugar", cleaned)
        self.assertIn("E621", cleaned)

    def test_clean_text_strips_common_prefixes_and_preserves_names_and_enums(self):
        raw = "Ingredients:  Wheat Flour,  Sugar,  E621"
        cleaned = clean_text(raw)
        self.assertEqual(cleaned, "Wheat Flour, Sugar, E621")

        # Test other common prefixes
        self.assertEqual(clean_text("Contains: Milk, Soy"), "Milk, Soy")
        self.assertEqual(clean_text("May contain: Peanuts, Tree Nuts"), "Peanuts, Tree Nuts")

    def test_parse_tokens_uses_cleaned_text(self):
        raw = "Ingredients:  Wheat Flour,  Sugar,  E621"
        tokens = self.analyzer.parse_tokens(raw)
        self.assertIn("Wheat Flour", tokens)
        self.assertIn("Sugar", tokens)
        self.assertIn("E621", tokens)
        self.assertEqual(len(tokens), 3)

    def test_parse_tokens_empty_and_none(self):
        self.assertEqual(self.analyzer.parse_tokens(""), [])
        self.assertEqual(self.analyzer.parse_tokens("   "), [])
        self.assertEqual(self.analyzer.parse_tokens(None), [])


class TestIngredientMatching(unittest.TestCase):
    """Test ingredient matching logic: exact, case-insensitive, E-number, alias, and fuzzy."""

    def setUp(self):
        self.analyzer = IngredientAnalyzer()

    def test_exact_name_match(self):
        item, confidence = self.analyzer.match_ingredient("Citric acid")
        self.assertIsNotNone(item)
        self.assertEqual(item['name'], "Citric acid")
        self.assertEqual(confidence, 100.0)

    def test_case_insensitive_match(self):
        item, confidence = self.analyzer.match_ingredient("citric acid")
        self.assertIsNotNone(item)
        self.assertEqual(item['name'], "Citric acid")
        self.assertEqual(confidence, 100.0)

        item_upper, _ = self.analyzer.match_ingredient("SUGAR")
        self.assertIsNotNone(item_upper)
        self.assertEqual(item_upper['name'], "Sugar")

    def test_e_number_matching(self):
        # Direct E621 match for Monosodium glutamate
        item, confidence = self.analyzer.match_ingredient("E621")
        self.assertIsNotNone(item)
        self.assertEqual(item['name'], "Monosodium glutamate")
        self.assertEqual(confidence, 100.0)

        # Match with space / lowercase: e 330
        item_citric, _ = self.analyzer.match_ingredient("e 330")
        self.assertIsNotNone(item_citric)
        self.assertEqual(item_citric['name'], "Citric acid")

    def test_alias_matching(self):
        # Alias 'sodium glutamate' -> Monosodium glutamate
        item, confidence = self.analyzer.match_ingredient("sodium glutamate")
        self.assertIsNotNone(item)
        self.assertEqual(item['name'], "Monosodium glutamate")
        self.assertGreaterEqual(confidence, 90.0)

        # Alias 'whey' -> Milk powder
        item_whey, conf_whey = self.analyzer.match_ingredient("whey")
        self.assertIsNotNone(item_whey)
        self.assertEqual(item_whey['name'], "Milk powder")
        self.assertGreaterEqual(conf_whey, 90.0)

    def test_fuzzy_matching_for_typos(self):
        # 'caseen' -> Milk powder (alias casein)
        item, confidence = self.analyzer.match_ingredient("caseen")
        self.assertIsNotNone(item)
        self.assertEqual(item['name'], "Milk powder")
        self.assertGreaterEqual(confidence, 70.0)

    def test_unrelated_ingredient_no_false_match(self):
        item, confidence = self.analyzer.match_ingredient("xyzrandomgibberish98765")
        self.assertIsNone(item)
        self.assertEqual(confidence, 0.0)

    def test_search_ingredients_empty_and_whitespace(self):
        self.assertEqual(self.analyzer.search_ingredients(""), [])
        self.assertEqual(self.analyzer.search_ingredients("   "), [])
        self.assertEqual(self.analyzer.search_ingredients(None), [])

    def test_search_ingredients_exact_and_fuzzy(self):
        # Search E-number
        res_enum = self.analyzer.search_ingredients("E621")
        self.assertTrue(any(i['name'] == 'Monosodium glutamate' for i in res_enum))

        # Search alias
        res_alias = self.analyzer.search_ingredients("sodium glutamate")
        self.assertTrue(any(i['name'] == 'Monosodium glutamate' for i in res_alias))

        # Search typo
        res_typo = self.analyzer.search_ingredients("caseen")
        self.assertTrue(any(i['name'] == 'Milk powder' for i in res_typo))

        # Unrelated search
        res_none = self.analyzer.search_ingredients("xyzcompletelyunrelatedkeyword123")
        self.assertEqual(len(res_none), 0)


class TestSafetyScoring(unittest.TestCase):
    """Test safety score calculation, deduplication, thresholds, and override."""

    def setUp(self):
        self.analyzer = IngredientAnalyzer()

    def test_empty_or_no_match_baseline(self):
        # Empty detected list has baseline score 100
        score = self.analyzer.compute_score([])
        self.assertEqual(score, 100)

        # Analysis of empty text gives 100 score and 'Clean & Safe'
        res = self.analyzer.analyze("")
        self.assertEqual(res['safety_score'], 100)
        self.assertEqual(res['summary'], "Clean & Safe")

    def test_known_safe_ingredient_scoring(self):
        # Citric acid and Sugar are Safe (penalty = 0)
        res = self.analyzer.analyze("Sugar, Citric acid")
        self.assertEqual(res['safety_score'], 100)
        self.assertEqual(res['summary'], "Clean & Safe")

    def test_multiple_ingredients_different_safety_levels(self):
        # Tartrazine is Caution (-15), Potassium bromate is Harmful (-35)
        # Expected: 100 - 15 - 35 = 50
        detected = [
            {'name': 'Tartrazine', 'safety_level': 'Caution'},
            {'name': 'Potassium bromate', 'safety_level': 'Harmful'},
        ]
        score = self.analyzer.compute_score(detected)
        self.assertEqual(score, 50)

    def test_repeated_ingredients_do_not_inflate_penalty(self):
        # Passing duplicate caution ingredient should not penalize twice
        detected_with_dups = [
            {'name': 'Tartrazine', 'safety_level': 'Caution'},
            {'name': 'Tartrazine', 'safety_level': 'Caution'},
            {'name': 'Sugar', 'safety_level': 'Safe'},
        ]
        score = self.analyzer.compute_score(detected_with_dups)
        self.assertEqual(score, 85)  # Deducted 15 only once

    def test_score_clamping_to_zero_and_hundred(self):
        # Penalty exceeds 100 points
        many_harmful = [
            {'name': f'Harmful_{i}', 'safety_level': 'Harmful'} for i in range(5)
        ]
        score = self.analyzer.compute_score(many_harmful)
        self.assertEqual(score, 0)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)

    def test_verdict_agreement_with_thresholds(self):
        v85, badge85 = self.analyzer.score_to_verdict(85)
        self.assertEqual(v85, "Clean & Safe")
        self.assertEqual(badge85, "success")

        v60, badge60 = self.analyzer.score_to_verdict(60)
        self.assertEqual(v60, "Moderate Caution")
        self.assertEqual(badge60, "warning")

        v59, badge59 = self.analyzer.score_to_verdict(59)
        self.assertEqual(v59, "High Risk")
        self.assertEqual(badge59, "danger")

        v0, badge0 = self.analyzer.score_to_verdict(0)
        self.assertEqual(v0, "High Risk")
        self.assertEqual(badge0, "danger")

    def test_personal_allergy_override_sets_verdict_to_avoid_without_changing_score(self):
        # Milk powder has allergen_tag 'milk' and is classified as Safe (score penalty 0)
        res = self.analyzer.analyze(
            "Milk powder, Sugar",
            user_allergies=["milk"],
            user_diet="None"
        )
        # Score calculation is unaffected
        self.assertEqual(res['safety_score'], 100)
        self.assertEqual(res['base_verdict'], "Clean & Safe")
        # Displayed verdict is overridden to Avoid
        self.assertEqual(res['summary'], "Avoid")
        self.assertEqual(res['badge_class'], "danger")
        self.assertTrue(res['has_conflict'])
        self.assertTrue(any("milk" in c['message'].lower() for c in res['personal_conflicts']))

    def test_personal_diet_override_sets_verdict_to_avoid(self):
        # Gelatin has diet_flags 'vegetarian, vegan' conflict and is classified as Safe
        res = self.analyzer.analyze(
            "Gelatin, Sugar",
            user_allergies=[],
            user_diet="vegan"
        )
        self.assertEqual(res['summary'], "Avoid")
        self.assertTrue(res['has_conflict'])


if __name__ == '__main__':
    unittest.main()
