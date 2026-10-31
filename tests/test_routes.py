import io
import unittest
from app import create_app, db
from app.models.ingredient import Ingredient, Scan
from app.models.user import User
from database import load_ingredients_from_csv


class TestAppRoutesAndSecurity(unittest.TestCase):
    """Test Flask routes, scan history, database isolation, auth gate, and security controls."""

    def setUp(self):
        self.app = create_app('testing')
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()

        # Build in-memory database schema and seed ingredients
        db.create_all()
        load_ingredients_from_csv(app=self.app)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def login(self, username='routewriter', email='routewriter@example.com', password='password123'):
        user = User.query.filter_by(username=username).first()
        if not user:
            user = User(username=username, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
        self.client.post('/auth/login', data={'username': username, 'password': password})
        return user

    def test_database_isolation(self):
        """Verify tests run on in-memory database and don't touch production DB."""
        self.assertEqual(self.app.config['SQLALCHEMY_DATABASE_URI'], 'sqlite:///:memory:')
        self.assertTrue(self.app.config['TESTING'])

    def test_landing_page(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Know What's Inside", html)
        self.assertIn("Scan Ingredients", html)

    def test_navigation_routes(self):
        # Public endpoints load with HTTP 200
        for route in ['/', '/scan', '/search', '/auth/login', '/auth/register']:
            response = self.client.get(route)
            self.assertEqual(response.status_code, 200, f"Failed on route {route}")

        # Unauthenticated guest requesting /history is redirected to login (302)
        guest_resp = self.client.get('/history')
        self.assertEqual(guest_resp.status_code, 302)
        self.assertIn('/auth/login', guest_resp.headers.get('Location', ''))

        # Authenticated user can view /history (200)
        self.login()
        auth_resp = self.client.get('/history')
        self.assertEqual(auth_resp.status_code, 200)

    def test_custom_404_page(self):
        response = self.client.get('/definitely-nonexistent-route-404')
        self.assertEqual(response.status_code, 404)
        html = response.get_data(as_text=True)
        self.assertIn("404", html)
        self.assertIn("Page Not Found", html)

    def test_guest_scan_redirects_to_login_and_claims_on_auth(self):
        """Authentication Gate: Unauthenticated guest submits scan -> redirected to login.
        Pending scan is preserved in session, and claimed upon subsequent login/registration."""
        # 1. Guest submits scan
        response = self.client.post('/scan', data={
            'product_name': 'Pending Guest Cereal',
            'raw_text': 'Wheat Flour, Sugar, Citric acid',
            'allergies': [],
            'diet': 'None'
        }, follow_redirects=False)

        # Must redirect to login with next parameter
        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/login', response.headers.get('Location', ''))

        # Scan was saved in DB without owner initially
        scan = Scan.query.filter_by(product_name='Pending Guest Cereal').first()
        self.assertIsNotNone(scan)
        self.assertIsNone(scan.user_id)

        # 2. Guest attempts to directly view /scan/<id> before logging in -> must redirect to login
        direct_resp = self.client.get(f'/scan/{scan.id}')
        self.assertEqual(direct_resp.status_code, 302)
        self.assertIn('/auth/login', direct_resp.headers.get('Location', ''))

        # 3. User logs in -> pending scan is claimed by the user and redirects to scan view
        user = User(username='claimuser', email='claimuser@example.com')
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()

        login_resp = self.client.post('/auth/login', data={
            'username': 'claimuser',
            'password': 'password123'
        }, follow_redirects=False)

        self.assertEqual(login_resp.status_code, 302)
        self.assertIn(f'/scan/{scan.id}', login_resp.headers.get('Location', ''))

        # Scan is now claimed
        db.session.refresh(scan)
        self.assertEqual(scan.user_id, user.id)

        # Now view scan results
        view_resp = self.client.get(f'/scan/{scan.id}')
        self.assertEqual(view_resp.status_code, 200)
        self.assertIn('Pending Guest Cereal', view_resp.get_data(as_text=True))

    def test_authenticated_text_scan_submission_and_persistence(self):
        """Authenticated user scan is saved directly with user_id and viewable in history."""
        user = self.login()
        response = self.client.post('/scan', data={
            'product_name': 'Morning Cereal',
            'raw_text': 'Wheat Flour, Sugar, Citric acid',
            'allergies': [],
            'diet': 'None'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        # Check saved scan
        scan = Scan.query.filter_by(product_name='Morning Cereal').first()
        self.assertIsNotNone(scan)
        self.assertEqual(scan.user_id, user.id)
        self.assertEqual(scan.score, 100)
        self.assertEqual(scan.verdict, 'Clean & Safe')

        # Check in history
        hist_resp = self.client.get('/history')
        self.assertEqual(hist_resp.status_code, 200)
        self.assertIn(f'#{scan.id}', hist_resp.get_data(as_text=True))
        self.assertIn('Clean & Safe', hist_resp.get_data(as_text=True))

        # Check view scan by id
        view_resp = self.client.get(f'/scan/{scan.id}')
        self.assertEqual(view_resp.status_code, 200)
        self.assertIn('Morning Cereal', view_resp.get_data(as_text=True))

    def test_allergy_avoid_persisted_to_database(self):
        self.login()
        response = self.client.post('/scan', data={
            'product_name': 'Dairy Treat',
            'raw_text': 'Milk powder, Sugar',
            'allergies': ['milk'],
            'diet': 'None'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        scan = Scan.query.filter_by(product_name='Dairy Treat').first()
        self.assertIsNotNone(scan)
        self.assertEqual(scan.verdict, 'Avoid')

    def test_invalid_scan_id_returns_404(self):
        self.login()
        response = self.client.get('/scan/999999')
        self.assertEqual(response.status_code, 404)

    def test_fake_image_upload_rejected_by_security(self):
        """Verify uploaded files with image extension but invalid magic bytes are rejected."""
        self.login()
        fake_image_content = b"<?php echo 'malicious script'; ?>"
        data = {
            'product_name': 'Malicious Item',
            'label_image': (io.BytesIO(fake_image_content), 'malicious.png')
        }
        response = self.client.post('/scan', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Invalid or corrupted image file", html)

    def test_access_control_on_user_scan(self):
        """Scans belonging to an authenticated user cannot be accessed by unauthenticated guests
        or another registered user."""
        owner = User(username='owneruser', email='owner@example.com')
        owner.set_password('password123')
        db.session.add(owner)
        db.session.commit()

        scan = Scan(
            user_id=owner.id,
            product_name='Private User Scan',
            extracted_text='Sugar, Citric acid',
            score=100,
            verdict='Clean & Safe'
        )
        db.session.add(scan)
        db.session.commit()

        # 1. Unauthenticated guest tries to view -> redirected to login (302)
        guest_view = self.client.get(f'/scan/{scan.id}')
        self.assertEqual(guest_view.status_code, 302)

        guest_export = self.client.get(f'/export-report/{scan.id}')
        self.assertEqual(guest_export.status_code, 302)

        # 2. Authenticated different user tries to view User A's scan -> 403 Forbidden
        self.login(username='otheruser', email='other@example.com')

        view_resp = self.client.get(f'/scan/{scan.id}')
        self.assertEqual(view_resp.status_code, 403)

        export_resp = self.client.get(f'/export-report/{scan.id}')
        self.assertEqual(export_resp.status_code, 403)

    def test_registration_validation(self):
        """Verify robust registration validation: email regex, min password length, duplicates."""
        # 1. Invalid email format
        r1 = self.client.post('/auth/register', data={
            'username': 'validuser1',
            'email': 'not-an-email-address',
            'password': 'password123',
            'confirm_password': 'password123'
        }, follow_redirects=True)
        self.assertIn("valid email address", r1.get_data(as_text=True))
        self.assertIsNone(User.query.filter_by(username='validuser1').first())

        # 2. Short password (< 6 chars)
        r2 = self.client.post('/auth/register', data={
            'username': 'validuser2',
            'email': 'user2@example.com',
            'password': '123',
            'confirm_password': '123'
        }, follow_redirects=True)
        self.assertIn("at least 6 characters", r2.get_data(as_text=True))
        self.assertIsNone(User.query.filter_by(username='validuser2').first())

        # 3. Password mismatch
        r3 = self.client.post('/auth/register', data={
            'username': 'validuser3',
            'email': 'user3@example.com',
            'password': 'password123',
            'confirm_password': 'password456'
        }, follow_redirects=True)
        self.assertIn("do not match", r3.get_data(as_text=True))

        # 4. Valid registration
        r4 = self.client.post('/auth/register', data={
            'username': 'validuser4',
            'email': 'User4@EXAMPLE.com',  # tests lowercase normalization
            'password': 'password123',
            'confirm_password': 'password123'
        }, follow_redirects=True)
        created = User.query.filter_by(username='validuser4').first()
        self.assertIsNotNone(created)
        self.assertEqual(created.email, 'user4@example.com')
        # Ensure password is not plaintext
        self.assertNotEqual(created.password_hash, 'password123')
        self.assertTrue(created.check_password('password123'))

        # Log out before testing duplicate registration as guest
        self.client.get('/auth/logout')

        # 5. Duplicate username prevention
        r5 = self.client.post('/auth/register', data={
            'username': 'validuser4',
            'email': 'distinct@example.com',
            'password': 'password123',
            'confirm_password': 'password123'
        }, follow_redirects=True)
        self.assertIn("already taken", r5.get_data(as_text=True))

    def test_child_suitability_and_regular_consumption(self):
        """Verify child suitability assessment and regular consumption analysis."""
        self.login()
        # Scan with Southampton dye (Tartrazine) and high sugar
        response = self.client.post('/scan', data={
            'product_name': 'Neon Chews',
            'raw_text': 'Sugar, Glucose Syrup, Citric Acid, Tartrazine (E102)',
            'allergies': [],
            'diet': 'None'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        scan = Scan.query.filter_by(product_name='Neon Chews').first()
        self.assertIsNotNone(scan)

        # Verify child suitability JSON
        child_eval = scan.child_suitability
        self.assertIsNotNone(child_eval)
        self.assertIn('Potential concern', child_eval.get('status', ''))
        self.assertIn('Southampton', ' '.join(child_eval.get('key_factors', [])))
        self.assertTrue(len(child_eval.get('disclaimer', '')) > 20)

        # Verify regular consumption JSON
        reg_eval = scan.regular_consumption
        self.assertIsNotNone(reg_eval)
        self.assertEqual(reg_eval.get('status'), 'Limit frequency')
        self.assertTrue(len(reg_eval.get('key_factors', [])) > 0)
        self.assertTrue(len(reg_eval.get('suggestions', [])) > 0)

        # HTML includes Child Suitability card & Regular Consumption card
        html = response.get_data(as_text=True)
        self.assertIn('Child Suitability', html)
        self.assertIn('Regular Consumption', html)
        self.assertIn('Can I consume or use this product regularly?', html)
        self.assertIn('Disclaimer:', html)

    def test_cosmetic_product_detection(self):
        """Verify non-food / cosmetic products are flagged as not for ingestion."""
        self.login()
        response = self.client.post('/scan', data={
            'product_name': 'Body Lotion',
            'raw_text': 'Water, Dimethicone, Methylparaben, Fragrance, Sodium Laureth Sulfate',
            'allergies': [],
            'diet': 'None'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        scan = Scan.query.filter_by(product_name='Body Lotion').first()
        self.assertIsNotNone(scan)
        self.assertIn('Not for ingestion', scan.child_suitability.get('status', ''))
        self.assertIn('External use only', scan.regular_consumption.get('status', ''))

    def test_unverified_ingredient_flagging(self):
        """Unverified ingredients are marked with safety_rating=Unknown and child_assessment=Insufficient information."""
        self.login()
        response = self.client.post('/scan', data={
            'product_name': 'Mysterious Snack',
            'raw_text': 'Sugar, Xylophytol-Nonexistent-Chemical-12345',
            'allergies': [],
            'diet': 'None'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        scan = Scan.query.filter_by(product_name='Mysterious Snack').first()
        self.assertIsNotNone(scan)
        unverified_count = scan.unrecognized_count
        self.assertGreaterEqual(unverified_count, 1)

        html = response.get_data(as_text=True)
        self.assertIn('Notice on Unverified Ingredients', html)
        self.assertIn('Insufficient information', html)

    def test_login_page_password_toggle_elements(self):
        """Verify show/hide password button attributes and structure on login page."""
        response = self.client.get('/auth/login')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        # Input must be hidden by default
        self.assertIn('type="password"', html)
        self.assertIn('id="password"', html)
        self.assertIn('name="password"', html)

        # Button must be type="button" so it never submits form
        self.assertIn('type="button"', html)
        self.assertIn('password-toggle-btn', html)
        self.assertIn('data-target="password"', html)

        # Accessible labels and icons
        self.assertIn('aria-label="Show password"', html)
        self.assertIn('title="Show password"', html)
        self.assertIn('bi bi-eye', html)

    def test_register_page_password_toggle_elements(self):
        """Verify independent show/hide password buttons on registration page for both password fields."""
        response = self.client.get('/auth/register')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        # Both inputs must be hidden by default
        self.assertEqual(html.count('type="password"'), 2)
        self.assertIn('id="password"', html)
        self.assertIn('id="confirm_password"', html)

        # Two independent toggle buttons with type="button"
        self.assertEqual(html.count('password-toggle-btn'), 2)
        self.assertEqual(html.count('type="button"'), 3)  # navbar-toggler + 2 password toggles

        # Targets
        self.assertIn('data-target="password"', html)
        self.assertIn('data-target="confirm_password"', html)

        # Accessible labels
        self.assertIn('aria-label="Show password"', html)
        self.assertIn('aria-label="Show confirm password"', html)
        self.assertGreaterEqual(html.count('bi bi-eye'), 2)


if __name__ == '__main__':
    unittest.main()
