import unittest
from app import create_app, db
from app.models.user import User
from app.services.analyzer_service import IngredientAnalyzer
from app.models.ingredient import Ingredient, Scan
from database import load_ingredients_from_csv


class TestBasicWorkflow(unittest.TestCase):
    """End-to-end integration and workflow tests using standard unittest."""

    def setUp(self):
        self.app = create_app('testing')
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def login(self, username='testuser', password='password123'):
        user = User.query.filter_by(username=username).first()
        if not user:
            user = User(username=username, email=f"{username}@example.com")
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
        return self.client.post('/auth/login', data={'username': username, 'password': password}, follow_redirects=True)

    def test_app_creation(self):
        """Verify application initializes with testing config."""
        self.assertIsNotNone(self.app)
        self.assertTrue(self.app.config['TESTING'])

    def test_landing_page(self):
        """Verify the landing page loads successfully and contains key app info."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Ingredient', html)
        self.assertIn("Know What's Inside", html)
        self.assertIn('Scan Ingredients', html)

    def test_navbar_links(self):
        """Verify navbar endpoints for guest and authenticated user."""
        public_endpoints = ['/', '/scan', '/search', '/auth/login', '/auth/register']
        for ep in public_endpoints:
            resp = self.client.get(ep)
            self.assertEqual(resp.status_code, 200, f"Endpoint {ep} returned status {resp.status_code}")

        # /history requires login (302 redirect for guest)
        guest_hist = self.client.get('/history')
        self.assertEqual(guest_hist.status_code, 302)

        # Authenticated user can access /history
        self.login()
        auth_hist = self.client.get('/history')
        self.assertEqual(auth_hist.status_code, 200)

    def test_404_error_page(self):
        """Verify custom 404 handler returns 404 status and error message."""
        response = self.client.get('/non-existent-route-for-testing')
        self.assertEqual(response.status_code, 404)
        html = response.get_data(as_text=True)
        self.assertIn('404', html)
        self.assertIn('Page Not Found', html)

    def test_ingredient_analyzer_service(self):
        """Verify analyzer parses tokens, detects allergens, and classifies risk."""
        analyzer = IngredientAnalyzer()
        sample_text = "Wheat Flour, Water, Tartrazine (E102), Soy Lecithin"
        result = analyzer.analyze(sample_text)

        self.assertIsNotNone(result)
        self.assertIn('detected_ingredients', result)
        self.assertIn('flagged_allergens', result)
        self.assertIn('summary', result)
        allergens = [a.lower() for a in result['flagged_allergens']]
        self.assertTrue(any('gluten' in a or 'wheat' in a for a in allergens))
        self.assertTrue(any('soy' in a for a in allergens))

    def test_scan_post_text(self):
        """Verify POST request to /scan performs analysis on raw text input for authenticated user."""
        self.login()
        load_ingredients_from_csv(app=self.app)
        response = self.client.post('/scan', data={
            'product_name': 'Test Snack',
            'raw_text': 'Wheat Flour, Citric Acid, Soy Lecithin'
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Test Snack', html)
        self.assertIn('Identified Ingredients Breakdown', html)
        self.assertIn('Test Snack', html)
        self.assertIn('Identified Ingredients Breakdown', html)

    def test_csv_loader_and_idempotence(self):
        """Verify loading ingredients from CSV and that repeated runs do not duplicate records."""
        count1 = load_ingredients_from_csv(app=self.app)
        self.assertEqual(count1, 80)
        self.assertEqual(Ingredient.query.count(), 80)

        # Second load (idempotence check)
        count2 = load_ingredients_from_csv(app=self.app)
        self.assertEqual(count2, 80)
        self.assertEqual(Ingredient.query.count(), 80)

    def test_csv_required_ingredients_query(self):
        """Verify required ingredients are present with correct data types."""
        load_ingredients_from_csv(app=self.app)

        sugar = Ingredient.query.filter_by(name='Sugar').first()
        self.assertIsNotNone(sugar)
        self.assertEqual(sugar.safety_level, 'Safe')
        self.assertFalse(sugar.banned_status)

        citric_acid = Ingredient.query.filter_by(name='Citric acid').first()
        self.assertIsNotNone(citric_acid)
        self.assertEqual(citric_acid.e_number, 'E330')
        self.assertEqual(citric_acid.safety_level, 'Safe')

        msg = Ingredient.query.filter_by(name='Monosodium glutamate').first()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.e_number, 'E621')

        banned_item = Ingredient.query.filter_by(name='Potassium bromate').first()
        self.assertIsNotNone(banned_item)
        self.assertEqual(banned_item.safety_level, 'Harmful')
        self.assertTrue(banned_item.banned_status)

    def test_scan_history_and_view_result(self):
        """Verify saving scan in SQLite scans table and retrieving it on history and view_scan."""
        self.login()
        load_ingredients_from_csv(app=self.app)

        resp = self.client.post('/scan', data={
            'product_name': 'Herbal Tea',
            'raw_text': 'Sugar, Citric acid',
            'allergies': [],
            'diet': 'None'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        scan = Scan.query.filter_by(product_name='Herbal Tea').first()
        self.assertIsNotNone(scan)
        self.assertIsNone(scan.image_filename)
        self.assertEqual(scan.score, 100)
        self.assertEqual(scan.verdict, 'Clean & Safe')
        self.assertIsNotNone(scan.scan_date)
        scan_id = scan.id

        # History page lists the scan
        hist_resp = self.client.get('/history')
        self.assertEqual(hist_resp.status_code, 200)
        hist_html = hist_resp.get_data(as_text=True)
        self.assertIn(f'#{scan_id}', hist_html)
        self.assertIn('Clean & Safe', hist_html)
        self.assertIn('View Result', hist_html)

        # View Result opens the specific scan
        view_resp = self.client.get(f'/scan/{scan_id}')
        self.assertEqual(view_resp.status_code, 200)
        view_html = view_resp.get_data(as_text=True)
        self.assertIn(f'Historical Scan #{scan_id}', view_html)
        self.assertIn('Sugar', view_html)
        self.assertIn('Citric acid', view_html)

        # Invalid scan ID returns 404
        bad_resp = self.client.get('/scan/999999')
        self.assertEqual(bad_resp.status_code, 404)

    def test_scan_allergy_avoid_verdict_persisted(self):
        """Verify allergy/diet override sets verdict to Avoid and persists in scans table."""
        self.login()
        load_ingredients_from_csv(app=self.app)

        resp = self.client.post('/scan', data={
            'product_name': 'Dairy Snack',
            'raw_text': 'Casein, Sugar',
            'allergies': ['milk'],
            'diet': 'None'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('Avoid — Personal Allergy/Diet Conflict', html)

        saved = Scan.query.filter_by(product_name='Dairy Snack').first()
        self.assertIsNotNone(saved)
        self.assertEqual(saved.verdict, 'Avoid')

        view_resp = self.client.get(f'/scan/{saved.id}')
        self.assertEqual(view_resp.status_code, 200)
        view_html = view_resp.get_data(as_text=True)
        self.assertIn('Avoid', view_html)
        self.assertIn('matches your selected milk allergy', view_html)

    def test_ingredient_search_exact_and_fuzzy(self):
        """Verify ingredient search with exact, alias, E-number, and fuzzy typo matching."""
        load_ingredients_from_csv(app=self.app)

        # 1. Search by E-number E621
        r_enum = self.client.get('/search?q=E621')
        self.assertEqual(r_enum.status_code, 200)
        self.assertIn('Monosodium glutamate', r_enum.get_data(as_text=True))

        # 2. Search by alias sodium glutamate
        r_alias = self.client.get('/search?q=sodium+glutamate')
        self.assertEqual(r_alias.status_code, 200)
        self.assertIn('Monosodium glutamate', r_alias.get_data(as_text=True))

        # 3. Search by alias whey -> Milk powder
        r_whey = self.client.get('/search?q=whey')
        self.assertEqual(r_whey.status_code, 200)
        self.assertIn('Milk powder', r_whey.get_data(as_text=True))

        # 4. Search typo caseen -> Milk powder
        r_typo = self.client.get('/search?q=caseen')
        self.assertEqual(r_typo.status_code, 200)
        self.assertIn('Milk powder', r_typo.get_data(as_text=True))

        # 5. Search non-existent word -> No matching ingredient found
        r_none = self.client.get('/search?q=xyznonexistentword123')
        self.assertEqual(r_none.status_code, 200)
        self.assertIn('No matching ingredient found', r_none.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
