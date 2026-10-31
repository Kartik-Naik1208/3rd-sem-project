"""
Comprehensive tests for IngredientIQ Logout Functionality,
Session Invalidation, Cookie Expiration, Navbar State, and Access Control.
"""

import unittest
from app import create_app, db
from app.models.user import User
from app.models.ingredient import Scan
from database import load_ingredients_from_csv


class TestLogoutWorkflowAndSecurity(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.client = self.app.test_client()
        db.create_all()
        load_ingredients_from_csv(app=self.app)

        # Create test user
        self.user = User(username='kartik', email='kartik@example.com', is_admin=False)
        self.user.set_password('MySecurePassword123!')

        # Create test admin
        self.admin = User(username='admin', email='admin@example.com', is_admin=True)
        self.admin.set_password('AdminPassword123!')

        db.session.add_all([self.user, self.admin])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def login_kartik(self, remember=True):
        return self.client.post('/auth/login', data={
            'username': 'kartik',
            'password': 'MySecurePassword123!',
            'remember': 'on' if remember else 'off'
        }, follow_redirects=True)

    def test_01_authenticated_user_navbar_displays_username_and_options(self):
        """Logged-in user navbar displays username, history, and logout dropdown."""
        resp = self.login_kartik()
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)

        # Displays username
        self.assertIn('kartik', html)
        self.assertIn('id="userDropdown"', html)
        self.assertIn('Logout', html)
        self.assertIn('href="/auth/logout"', html)

        # Authenticated options present
        self.assertIn('href="/history"', html)

        # Non-admin does not see admin
        self.assertNotIn('href="/admin"', html)

        # Login / Register dropdown should NOT be displayed
        self.assertNotIn('id="authDropdown"', html)

    def test_02_logout_redirects_to_home_with_flash_message(self):
        """Logout terminates session and redirects to public home with confirmation message."""
        self.login_kartik()

        # Call logout
        logout_resp = self.client.get('/auth/logout', follow_redirects=False)
        self.assertEqual(logout_resp.status_code, 302)
        self.assertEqual(logout_resp.headers.get('Location'), '/')

        # Follow redirect
        home_resp = self.client.get(logout_resp.headers.get('Location'))
        self.assertEqual(home_resp.status_code, 200)
        html = home_resp.get_data(as_text=True)

        # Flash message displayed
        self.assertIn('You have been logged out successfully.', html)

        # Username is removed
        self.assertNotIn('id="userDropdown"', html)
        self.assertNotIn('kartik', html)

        # User-only options removed from navbar
        self.assertNotIn('href="/history"', html)
        self.assertNotIn('Logout', html)

        # Login and Register options displayed
        self.assertIn('id="authDropdown"', html)
        self.assertIn('Login / Register', html)
        self.assertIn('href="/auth/login"', html)
        self.assertIn('href="/auth/register"', html)

    def test_03_logout_deletes_remember_cookie(self):
        """Logout explicitly sets deletion headers for remember_token."""
        self.login_kartik(remember=True)

        logout_resp = self.client.get('/auth/logout', follow_redirects=False)
        self.assertEqual(logout_resp.status_code, 302)

        # Check Set-Cookie deletion headers
        set_cookies = logout_resp.headers.getlist('Set-Cookie')
        remember_deleted = any('remember_token=' in c and ('expires=Thu, 01 Jan 1970' in c or 'Max-Age=0' in c) for c in set_cookies)
        self.assertTrue(remember_deleted, f"Remember cookie deletion not found in Set-Cookie: {set_cookies}")

    def test_04_cache_control_headers_prevent_browser_caching(self):
        """Sensitive authenticated responses include strict no-cache headers."""
        self.login_kartik()

        # Check authenticated page
        resp = self.client.get('/history')
        self.assertEqual(resp.status_code, 200)
        cache_control = resp.headers.get('Cache-Control', '')
        self.assertIn('no-store', cache_control)
        self.assertIn('private', cache_control)
        self.assertEqual(resp.headers.get('Pragma'), 'no-cache')

        # Check logout response
        logout_resp = self.client.get('/auth/logout')
        l_cc = logout_resp.headers.get('Cache-Control', '')
        self.assertIn('no-store', l_cc)

    def test_05_cannot_access_history_after_logout(self):
        """Logged-out user cannot access /history; redirected to login."""
        self.login_kartik()
        self.client.get('/auth/logout')

        # Attempt to access /history directly
        resp = self.client.get('/history', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/auth/login', resp.headers.get('Location', ''))

        # Follow to login page and check message
        login_page = self.client.get(resp.headers.get('Location'))
        self.assertEqual(login_page.status_code, 200)
        self.assertIn('Please log in to continue.', login_page.get_data(as_text=True))

    def test_06_cannot_access_dashboard_after_logout(self):
        """Logged-out user cannot access /dashboard; redirected to login."""
        self.login_kartik()
        self.client.get('/auth/logout')

        resp = self.client.get('/dashboard', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/auth/login', resp.headers.get('Location', ''))

    def test_07_cannot_access_protected_scan_results_after_logout(self):
        """Logged-out user cannot access /scan/<id>/results; redirected to login."""
        # Create a scan owned by kartik
        scan = Scan(
            user_id=self.user.id,
            product_name="Kartik Private Cereal",
            extracted_text="Wheat, Milk, Sugar",
            score=88,
            verdict="Safe",
            detected_ingredients=[{'canonical_name': 'Wheat', 'raw_token': 'Wheat'}],
            child_suitability={'status': 'Safe', 'simple_status': 'No concern', 'badge_class': 'success', 'summary': 'OK'},
            regular_consumption={'status': 'Reasonable', 'simple_status': 'Reasonable', 'badge_class': 'success', 'summary': 'OK'}
        )
        db.session.add(scan)
        db.session.commit()

        # Log in and verify kartik can access scan
        self.login_kartik()
        auth_resp = self.client.get(f'/scan/{scan.id}/results')
        self.assertEqual(auth_resp.status_code, 200)
        self.assertIn("Kartik Private Cereal", auth_resp.get_data(as_text=True))

        # Log out
        self.client.get('/auth/logout')

        # Now try to access protected scan results
        unauth_resp = self.client.get(f'/scan/{scan.id}/results', follow_redirects=False)
        self.assertEqual(unauth_resp.status_code, 302)
        self.assertIn('/auth/login', unauth_resp.headers.get('Location', ''))

    def test_08_cannot_access_admin_after_logout(self):
        """Logged-out user cannot access /admin or admin actions; redirected to login."""
        resp = self.client.get('/admin', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/auth/login', resp.headers.get('Location', ''))

        post_resp = self.client.post('/admin/ingredient/add', data={'name': 'HackedIngredient'}, follow_redirects=False)
        self.assertEqual(post_resp.status_code, 302)
        self.assertIn('/auth/login', post_resp.headers.get('Location', ''))

    def test_09_relogin_restores_all_authenticated_functionality(self):
        """User can log back in seamlessly after logging out."""
        # 1. Login
        self.login_kartik()

        # 2. Logout
        self.client.get('/auth/logout')

        # 3. Relogin
        relogin_resp = self.login_kartik()
        self.assertEqual(relogin_resp.status_code, 200)
        html = relogin_resp.get_data(as_text=True)

        self.assertIn('kartik', html)
        self.assertIn('href="/auth/logout"', html)
        self.assertIn('href="/history"', html)

        # History is accessible again
        hist_resp = self.client.get('/history')
        self.assertEqual(hist_resp.status_code, 200)

    def test_10_admin_navbar_visibility(self):
        """Admin user sees Admin nav item; regular user does not; guest does not."""
        # 1. Guest
        guest_html = self.client.get('/').get_data(as_text=True)
        self.assertNotIn('href="/admin"', guest_html)

        # 2. Regular user (kartik)
        self.login_kartik()
        user_html = self.client.get('/').get_data(as_text=True)
        self.assertNotIn('href="/admin"', user_html)
        self.client.get('/auth/logout')

        # 3. Admin user
        self.client.post('/auth/login', data={
            'username': 'admin',
            'password': 'AdminPassword123!'
        }, follow_redirects=True)
        admin_html = self.client.get('/').get_data(as_text=True)
        self.assertIn('href="/admin"', admin_html)
        self.assertIn('admin', admin_html)


if __name__ == '__main__':
    unittest.main()
