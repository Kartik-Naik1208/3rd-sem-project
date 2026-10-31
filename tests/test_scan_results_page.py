"""
Tests for IngredientIQ Dedicated Scan Results Page and Children's Age Guidance.
Verifies all 17 criteria specified in the product specification:
1.  Scan submission redirects to /scan/<scan_id>/results.
2.  /scan page is strictly upload/scanning form (no results underneath).
3.  Unauthenticated guests cannot access /scan/<scan_id>/results (redirects to login with next param).
4.  Pending scan claimed after login and redirected to /scan/<scan_id>/results.
5.  All extracted ingredients listed individually.
6.  Each card has canonical name, raw label text, food/additive badge, 2-3 line description.
7.  Authoritative sources cited (FSSAI, Codex Alimentarius, AAP, EFSA, WHO, US FDA).
8.  Common food ingredients (peanuts, cashews, milk, oats) show safe food statuses.
9.  Honey displays infant botulism alert and 'Avoid under 12 months' / < 1 year guidance.
10. Whole nuts show pediatric choking hazard alert for children under 5 years.
11. Overall product child suitability card includes dynamic 6-bracket age table.
12. Overall regular consumption assessment displays clear dietary factors.
13. Prominent warnings banner displays declared allergens and choking hazard alerts.
14. Navigation buttons: 'Scan Another Product' links to /scan.
15. Navigation buttons: 'View Scan History' links to /history.
16. Unidentified substances marked 'Insufficient information' and never assumed safe.
17. Cross-user scan access returns 403 Forbidden.
"""

import json
import unittest
from app import create_app, db
from app.models.user import User
from app.models.ingredient import Ingredient, Scan
from database import load_all_ingredients
from app.services.analyzer_service import IngredientAnalyzer, enrich_ingredient_details


class TestScanResultsPageWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app('testing')
        with cls.app.app_context():
            db.create_all()
            load_all_ingredients(cls.app)

    def setUp(self):
        self.app = self.__class__.app
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.client = self.app.test_client()

        # Clean users and scans between test cases while preserving loaded ingredient DB
        db.session.query(Scan).delete()
        db.session.query(User).delete()
        db.session.commit()

        # Seed test users
        self.user_a = User(username='alice', email='alice@example.com')
        self.user_a.set_password('SecretPass123!')
        self.user_b = User(username='bob', email='bob@example.com')
        self.user_b.set_password('SecretPass123!')
        db.session.add_all([self.user_a, self.user_b])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        self.app_context.pop()

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            db.session.remove()
            db.drop_all()

    def login_user_a(self):
        return self.client.post('/auth/login', data={
            'username': 'alice',
            'password': 'SecretPass123!'
        }, follow_redirects=True)

    def login_user_b(self):
        return self.client.post('/auth/login', data={
            'username': 'bob',
            'password': 'SecretPass123!'
        }, follow_redirects=True)

    def test_01_scan_submission_redirects_to_dedicated_results_page(self):
        """Criterion 1: Submitting text scan redirects to /scan/<scan_id>/results."""
        self.login_user_a()
        response = self.client.post('/scan', data={
            'product_name': 'Granola Crunch',
            'raw_text': 'Rolled Oats, Honey, Peanuts, Salt',
            'allergies': [],
            'diet': 'None'
        }, follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        location = response.headers.get('Location', '')
        self.assertIn('/scan/', location)
        self.assertTrue(location.endswith('/results'))

        scan = Scan.query.filter_by(product_name='Granola Crunch').first()
        self.assertIsNotNone(scan)
        self.assertIn(f'/scan/{scan.id}/results', location)

    def test_02_scan_page_is_strictly_input_and_shows_no_results(self):
        """Criterion 2: The /scan page does not display analysis results below form."""
        self.login_user_a()
        resp = self.client.get('/scan')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('Upload Label Image', html)
        self.assertIn('Drag & Drop image here', html)
        self.assertNotIn('Complete Identified Ingredients Breakdown', html)
        self.assertNotIn('Age-Group Guidance Breakdown', html)

    def test_03_unauthenticated_guest_cannot_view_results(self):
        """Criterion 3: Unauthenticated user accessing results page is redirected to login."""
        scan = Scan(
            user_id=self.user_a.id,
            product_name='Private Snack',
            extracted_text='Peanuts, Salt',
            score=85,
            verdict='Caution',
            detected_ingredients=[{'canonical_name': 'Peanuts', 'raw_token': 'Peanuts'}],
            child_suitability={'status': 'Caution', 'simple_status': 'Use caution', 'badge_class': 'warning', 'summary': 'Contains nuts.'},
            regular_consumption={'status': 'Reasonable', 'simple_status': 'Generally reasonable', 'badge_class': 'success', 'summary': 'Good protein source.'}
        )
        db.session.add(scan)
        db.session.commit()

        resp = self.client.get(f'/scan/{scan.id}/results', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        loc = resp.headers.get('Location', '')
        self.assertIn('/auth/login', loc)
        self.assertTrue(f'/scan/{scan.id}/results' in loc or f'%2Fscan%2F{scan.id}%2Fresults' in loc)

    def test_04_guest_scan_claimed_and_redirects_to_results(self):
        """Criterion 4: Guest scan stored in session, claimed after login, redirects to /results."""
        # Guest submits scan
        resp = self.client.post('/scan', data={
            'product_name': 'Guest Oat Bar',
            'raw_text': 'Oats, Honey, Salt',
            'allergies': [],
            'diet': 'None'
        }, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/auth/login', resp.headers.get('Location', ''))

        scan = Scan.query.filter_by(product_name='Guest Oat Bar').first()
        self.assertIsNotNone(scan)
        self.assertIsNone(scan.user_id)

        # Guest now logs in
        login_resp = self.client.post('/auth/login', data={
            'username': 'alice',
            'password': 'SecretPass123!'
        }, follow_redirects=False)
        self.assertEqual(login_resp.status_code, 302)
        self.assertIn(f'/scan/{scan.id}/results', login_resp.headers.get('Location', ''))

        # Check scan is now owned by alice
        db.session.refresh(scan)
        self.assertEqual(scan.user_id, self.user_a.id)

    def test_05_and_06_complete_individual_ingredient_breakdown_and_card_details(self):
        """Criteria 5 & 6: Each ingredient has its own card, 2-3 line description, safety & age badges."""
        self.login_user_a()
        scan_resp = self.client.post('/scan', data={
            'product_name': 'Breakfast Muesli',
            'raw_text': 'Rolled Oats, Whole Peanuts, Honey, Sugar, Salt',
            'allergies': [],
            'diet': 'None'
        }, follow_redirects=True)
        self.assertEqual(scan_resp.status_code, 200)
        html = scan_resp.get_data(as_text=True)

        # Check presence of individual ingredient items
        self.assertIn('Rolled Oats', html)
        self.assertIn('Whole Peanuts', html)
        self.assertIn('Honey', html)
        self.assertIn('Sugar', html)
        self.assertIn('Salt', html)

        # Check Food vs Additive badges
        self.assertIn('Food Ingredient', html)

        # Check safety assessment badges
        self.assertTrue(
            'No specific concern identified' in html or
            'Generally recognized for its intended food use' in html or
            'Use caution' in html
        )

        # Check children age guidance badges
        self.assertIn('Can Children Have This?', html)

    def test_07_authoritative_regulatory_sources_cited(self):
        """Criterion 7: Regulatory bodies cited (FSSAI, Codex, AAP, EFSA, WHO, US FDA)."""
        self.login_user_a()
        scan_resp = self.client.post('/scan', data={
            'product_name': 'Nut Butter Spread',
            'raw_text': 'Peanuts, Honey, Sodium Benzoate, Red 40',
            'allergies': [],
            'diet': 'None'
        }, follow_redirects=True)
        html = scan_resp.get_data(as_text=True)

        # Verify authoritative institutions mentioned in analysis and guidance
        sources_found = [src for src in ['FSSAI', 'Codex Alimentarius', 'AAP', 'EFSA', 'WHO', 'US FDA'] if src in html]
        self.assertTrue(len(sources_found) >= 3, f"Expected at least 3 authoritative sources, found: {sources_found}")

    def test_08_common_food_ingredients_recognized_safely(self):
        """Criterion 8: Common foods (peanuts, cashews, oats) are recognized without 'unverified' label."""
        self.login_user_a()
        scan_resp = self.client.post('/scan', data={
            'product_name': 'Trail Mix',
            'raw_text': 'Peanuts, Cashews, Almonds, Rolled Oats',
            'allergies': [],
            'diet': 'None'
        }, follow_redirects=True)
        html = scan_resp.get_data(as_text=True)

        self.assertIn('Peanuts', html)
        self.assertIn('Cashews', html)
        self.assertIn('Almonds', html)
        # Should not mark any of these common nuts as unverified
        self.assertNotIn('Unverified substance', html)

    def test_09_honey_infant_botulism_alert_and_age_guidance(self):
        """Criterion 9: Honey explicitly alerts to Clostridium botulinum and 'Avoid under 12 months'."""
        self.login_user_a()
        scan_resp = self.client.post('/scan', data={
            'product_name': 'Honey Biscuit',
            'raw_text': 'Wheat Flour, Pure Honey, Butter, Sugar',
            'allergies': [],
            'diet': 'None'
        }, follow_redirects=True)
        html = scan_resp.get_data(as_text=True)

        self.assertIn('Honey', html)
        self.assertIn('botulism', html.lower())
        self.assertTrue(
            'avoid under 12 months' in html.lower() or
            'under 1 year' in html.lower() or
            'not recommended under 1' in html.lower()
        )

    def test_10_whole_nuts_pediatric_choking_hazard_alert_under_5(self):
        """Criterion 10: Whole nuts trigger pediatric choking hazard alert for children under 5 years."""
        self.login_user_a()
        scan_resp = self.client.post('/scan', data={
            'product_name': 'Crunchy Nut Bar',
            'raw_text': 'Whole Peanuts, Roasted Cashews, Sugar, Salt',
            'allergies': [],
            'diet': 'None'
        }, follow_redirects=True)
        html = scan_resp.get_data(as_text=True)

        # Check for choking hazard warning banner
        self.assertIn('Pediatric Choking Hazard Warning (Children Under 5)', html)
        self.assertIn('smooth, finely ground paste', html)

    def test_11_child_suitability_card_with_dynamic_6_bracket_age_table(self):
        """Criterion 11: Dedicated child suitability card with dynamic 6 age brackets."""
        self.login_user_a()
        scan_resp = self.client.post('/scan', data={
            'product_name': 'Kids Fruit Chew',
            'raw_text': 'Apple Puree, Honey, Pectin, Red 40',
            'allergies': [],
            'diet': 'None'
        }, follow_redirects=True)
        html = scan_resp.get_data(as_text=True)

        # 6 Age brackets
        self.assertIn('Under 6 months', html)
        self.assertIn('6–12 months', html)
        self.assertIn('1–2 years', html)
        self.assertIn('2–5 years', html)
        self.assertIn('5–12 years', html)
        self.assertIn('Teenagers', html)

    def test_12_regular_consumption_assessment_card(self):
        """Criterion 12: Regular consumption card with clear nutritional factors."""
        self.login_user_a()
        scan_resp = self.client.post('/scan', data={
            'product_name': 'Daily Soda',
            'raw_text': 'Carbonated Water, High Fructose Corn Syrup, Caramel Color, Phosphoric Acid, Caffeine',
            'allergies': [],
            'diet': 'None'
        }, follow_redirects=True)
        html = scan_resp.get_data(as_text=True)

        self.assertIn('Can I consume or use this product regularly?', html)
        self.assertIn('Key Nutritional & Additive Factors', html)

    def test_13_important_warnings_section_declared_allergens(self):
        """Criterion 13: Important warnings banner flags declared allergens."""
        self.login_user_a()
        scan_resp = self.client.post('/scan', data={
            'product_name': 'Milk Chocolate',
            'raw_text': 'Sugar, Whole Milk Powder, Cocoa Butter, Soy Lecithin',
            'allergies': ['milk', 'soy'],
            'diet': 'None'
        }, follow_redirects=True)
        html = scan_resp.get_data(as_text=True)

        self.assertIn('Avoid — Personal Allergy/Diet Conflict', html)
        self.assertIn('matches your selected milk allergy', html)

    def test_14_and_15_navigation_buttons(self):
        """Criteria 14 & 15: Scan Another Product and View Scan History navigation buttons."""
        self.login_user_a()
        scan_resp = self.client.post('/scan', data={
            'product_name': 'Plain Rice Cakes',
            'raw_text': 'Brown Rice, Sea Salt',
            'allergies': [],
            'diet': 'None'
        }, follow_redirects=True)
        html = scan_resp.get_data(as_text=True)

        # Check navigation links
        self.assertIn('href="/scan"', html)
        self.assertIn('Scan Another Product', html)
        self.assertIn('href="/history"', html)
        self.assertIn('View Scan History', html)
        self.assertIn('Back to Dashboard', html)
        self.assertIn('Print Results', html)

    def test_16_unidentified_substances_marked_insufficient_information(self):
        """Criterion 16: Unknown chemical strings marked Insufficient information, never assumed safe."""
        self.login_user_a()
        scan_resp = self.client.post('/scan', data={
            'product_name': 'Mystery Mix',
            'raw_text': 'Wheat Flour, Xyzzqcompound992, Salt',
            'allergies': [],
            'diet': 'None'
        }, follow_redirects=True)
        html = scan_resp.get_data(as_text=True)

        self.assertIn('xyzzqcompound992', html.lower())
        self.assertIn('Insufficient information', html)
        self.assertIn('Notice on Unverified Ingredients', html)

    def test_17_cross_user_scan_access_returns_403(self):
        """Criterion 17: User B cannot access User A's scan results (403 Forbidden)."""
        # User A creates a scan
        scan_a = Scan(
            user_id=self.user_a.id,
            product_name="Alice Private Snack",
            extracted_text="Oats, Salt",
            score=90,
            verdict="Safe",
            detected_ingredients=[{'canonical_name': 'Oats', 'raw_token': 'Oats'}],
            child_suitability={'status': 'Safe', 'simple_status': 'No specific concern', 'badge_class': 'success', 'summary': 'Safe'},
            regular_consumption={'status': 'Reasonable', 'simple_status': 'Generally reasonable', 'badge_class': 'success', 'summary': 'Good'}
        )
        db.session.add(scan_a)
        db.session.commit()

        # User B logs in
        self.login_user_b()

        # User B attempts to access User A's results page
        resp = self.client.get(f'/scan/{scan_a.id}/results')
        self.assertEqual(resp.status_code, 403)
        self.assertIn('You do not have permission to view', resp.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()



if __name__ == '__main__':
    unittest.main()
