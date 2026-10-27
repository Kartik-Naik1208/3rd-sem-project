import io
import unittest
from app import create_app, db
from app.models.ingredient import Ingredient, Scan
from database import load_ingredients_from_csv


class TestAppRoutesAndSecurity(unittest.TestCase):
    """Test Flask routes, scan history, database isolation, and security controls."""

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
        for route in ['/', '/scan', '/history', '/search', '/admin', '/auth/login', '/auth/register']:
            response = self.client.get(route)
            self.assertEqual(response.status_code, 200, f"Failed on route {route}")

    def test_custom_404_page(self):
        response = self.client.get('/definitely-nonexistent-route-404')
        self.assertEqual(response.status_code, 404)
        html = response.get_data(as_text=True)
        self.assertIn("404", html)
        self.assertIn("Page Not Found", html)

    def test_text_scan_submission_and_persistence(self):
        response = self.client.post('/scan', data={
            'product_name': 'Morning Cereal',
            'raw_text': 'Wheat Flour, Sugar, Citric acid',
            'allergies': [],
            'diet': 'None'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        # Check saved scan in in-memory database
        scan = Scan.query.filter_by(product_name='Morning Cereal').first()
        self.assertIsNotNone(scan)
        self.assertIsNone(scan.image_filename)  # text-only has NULL image
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
        response = self.client.get('/scan/999999')
        self.assertEqual(response.status_code, 404)

    def test_fake_image_upload_rejected_by_security(self):
        """Verify uploaded files with image extension but invalid magic bytes are rejected."""
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
        """Scans belonging to an authenticated user cannot be accessed by unauthenticated guests."""
        scan = Scan(
            user_id=42,  # Owned by a registered user
            product_name='Private User Scan',
            extracted_text='Sugar, Citric acid',
            score=100,
            verdict='Clean & Safe'
        )
        db.session.add(scan)
        db.session.commit()

        # Guest tries to view private user scan
        view_resp = self.client.get(f'/scan/{scan.id}')
        self.assertEqual(view_resp.status_code, 403)

        # Guest tries to export report for private user scan
        export_resp = self.client.get(f'/export-report/{scan.id}')
        self.assertEqual(export_resp.status_code, 403)


if __name__ == '__main__':
    unittest.main()
