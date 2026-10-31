import html as html_lib
import smtplib
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from app import create_app, db
from app.models.user import User, PasswordResetToken
from app.models.ingredient import Ingredient, Scan
from werkzeug.security import check_password_hash


class TestPasswordResetWorkflow(unittest.TestCase):
    """
    Comprehensive verification for IngredientIQ Forgot Password and Reset Password system.
    Covers all 20 required test scenarios with mocked SMTP delivery.
    """

    def setUp(self):
        self.app = create_app('testing')
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        # Seed test user 1 (primary)
        self.user1 = User(username='registereduser', email='user@example.com')
        self.user1.set_password('oldPassword123')
        db.session.add(self.user1)

        # Seed test user 2 (cross-user isolation test)
        self.user2 = User(username='otheruser', email='other@example.com')
        self.user2.set_password('otherPassword456')
        db.session.add(self.user2)

        # Seed an ingredient to ensure database integrity is intact
        self.ing = Ingredient(name='Citric Acid', safety_level='Safe', banned_status=False)
        db.session.add(self.ing)

        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    # 1. The Forgot Password link appears on the login page
    def test_01_forgot_password_link_on_login_page(self):
        response = self.client.get('/auth/login')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Forgot Password?', html)
        self.assertIn('/auth/forgot-password', html)

    # 2. An invalid email format is rejected
    def test_02_invalid_email_format_rejected(self):
        invalid_emails = ['notanemail', 'missingatsign.com', 'user@', 'user@domain']
        for bad_email in invalid_emails:
            response = self.client.post(
                '/auth/forgot-password',
                data={'email': bad_email},
                follow_redirects=True
            )
            html = response.get_data(as_text=True)
            self.assertIn('Please enter a valid email address.', html)

    # 3. A registered email is found in the actual configured database
    @patch('smtplib.SMTP')
    def test_03_registered_email_found_in_database(self, mock_smtp_class):
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        # Test case-insensitivity and whitespace stripping
        response = self.client.post(
            '/auth/forgot-password',
            data={'email': '  USER@EXAMPLE.COM  '},
            follow_redirects=True
        )
        self.assertEqual(response.status_code, 200)
        # Verify token record was created in database linked to user1
        token_record = PasswordResetToken.query.filter_by(user_id=self.user1.id).first()
        self.assertIsNotNone(token_record)
        self.assertEqual(token_record.user_id, self.user1.id)
        self.assertFalse(token_record.used)

    # 4. An unregistered email shows the requested message and does not trigger an email
    @patch('smtplib.SMTP')
    def test_04_unregistered_email_shows_requested_message_and_no_email(self, mock_smtp_class):
        response = self.client.post(
            '/auth/forgot-password',
            data={'email': 'unregistered_person@example.com'},
            follow_redirects=True
        )
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        exact_msg = "This email address is not registered with IngredientIQ. Please check your email or create a new account."
        self.assertIn(exact_msg, html)
        # Verify no SMTP connection was attempted
        mock_smtp_class.assert_not_called()
        # Verify no token was created
        self.assertEqual(PasswordResetToken.query.count(), 0)

    # 5. A registered email triggers an attempt to send the reset email
    @patch('smtplib.SMTP')
    def test_05_registered_email_triggers_smtp_attempt(self, mock_smtp_class):
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        self.client.post(
            '/auth/forgot-password',
            data={'email': 'user@example.com'},
            follow_redirects=True
        )
        # Verify SMTP was called
        mock_smtp_class.assert_called_once()
        mock_server.send_message.assert_called_once()
        sent_msg = mock_server.send_message.call_args[0][0]
        self.assertEqual(sent_msg['Subject'], 'Reset Your IngredientIQ Password')
        self.assertEqual(sent_msg['To'], 'user@example.com')

    # 6. Successful email delivery displays the correct confirmation
    @patch('smtplib.SMTP')
    def test_06_successful_delivery_displays_correct_confirmation(self, mock_smtp_class):
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        response = self.client.post(
            '/auth/forgot-password',
            data={'email': 'user@example.com'},
            follow_redirects=True
        )
        html = response.get_data(as_text=True)
        exact_success_msg = "Password reset link sent successfully! Please check your email inbox."
        self.assertIn(exact_success_msg, html)

    # 7. SMTP failure does not falsely report success
    @patch('smtplib.SMTP')
    def test_07_smtp_failure_does_not_falsely_report_success(self, mock_smtp_class):
        # Configure SMTP to raise an exception simulating connection/auth failure
        mock_smtp_class.side_effect = smtplib.SMTPConnectError(421, b"Connection refused")

        response = self.client.post(
            '/auth/forgot-password',
            data={'email': 'user@example.com'},
            follow_redirects=True
        )
        html = html_lib.unescape(response.get_data(as_text=True))
        exact_fail_msg = "We couldn't send the reset email right now. Please try again later."
        self.assertIn(exact_fail_msg, html)
        self.assertNotIn("Password reset link sent successfully!", html)

    # 8. Reset tokens expire after 30 minutes
    def test_08_reset_tokens_expire_after_30_minutes(self):
        token_record, raw_token = PasswordResetToken.create_for_user(self.user1, expires_in_minutes=30)
        db.session.commit()

        # Check expiration delta is ~30 minutes
        delta = token_record.expires_at - token_record.created_at
        self.assertAlmostEqual(delta.total_seconds(), 30 * 60, delta=10)
        self.assertFalse(token_record.is_expired)

        # Fast-forward token into past (expired by 1 minute)
        token_record.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.session.commit()

        self.assertTrue(token_record.is_expired)
        rec, usr = PasswordResetToken.verify_token(raw_token)
        self.assertIsNone(rec)
        self.assertIsNone(usr)

    # 9. Invalid and expired tokens are rejected
    def test_09_invalid_and_expired_tokens_are_rejected(self):
        # 1. Non-existent token
        response = self.client.get('/auth/reset-password/totally-invalid-token')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('invalid or has expired', html)

        # 2. Expired token
        token_record, raw_token = PasswordResetToken.create_for_user(self.user1, expires_in_minutes=30)
        token_record.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        db.session.commit()

        response2 = self.client.get(f'/auth/reset-password/{raw_token}')
        html2 = response2.get_data(as_text=True)
        self.assertIn('invalid or has expired', html2)

    # 10. Reusing a successfully consumed token is rejected
    def test_10_reusing_consumed_token_is_rejected(self):
        token_record, raw_token = PasswordResetToken.create_for_user(self.user1)
        db.session.commit()

        # First consumption -> successful password reset
        resp1 = self.client.post(
            f'/auth/reset-password/{raw_token}',
            data={'password': 'brandNewPass123', 'confirm_password': 'brandNewPass123'},
            follow_redirects=True
        )
        self.assertEqual(resp1.status_code, 200)
        self.assertIn('Your password has been successfully reset!', resp1.get_data(as_text=True))

        # Check token is marked as used
        token_db = db.session.get(PasswordResetToken, token_record.id)
        self.assertTrue(token_db.used)
        self.assertIsNotNone(token_db.used_at)

        # Second attempt using same token must be rejected
        resp2 = self.client.get(f'/auth/reset-password/{raw_token}')
        self.assertIn('invalid or has expired', resp2.get_data(as_text=True))

        resp3 = self.client.post(
            f'/auth/reset-password/{raw_token}',
            data={'password': 'anotherPassword123', 'confirm_password': 'anotherPassword123'},
            follow_redirects=True
        )
        self.assertIn('invalid or has expired', resp3.get_data(as_text=True))

    # 11. Mismatched passwords are rejected
    def test_11_mismatched_passwords_rejected(self):
        _, raw_token = PasswordResetToken.create_for_user(self.user1)
        db.session.commit()

        response = self.client.post(
            f'/auth/reset-password/{raw_token}',
            data={'password': 'PasswordOne123', 'confirm_password': 'PasswordDifferent456'},
            follow_redirects=True
        )
        html = response.get_data(as_text=True)
        self.assertIn('Passwords do not match.', html)
        # Verify user's password remained unchanged
        u = db.session.get(User, self.user1.id)
        self.assertTrue(u.check_password('oldPassword123'))

    # 12. Weak passwords are rejected according to the password policy
    def test_12_weak_passwords_rejected(self):
        _, raw_token = PasswordResetToken.create_for_user(self.user1)
        db.session.commit()

        # Less than 6 characters
        response = self.client.post(
            f'/auth/reset-password/{raw_token}',
            data={'password': '12345', 'confirm_password': '12345'},
            follow_redirects=True
        )
        html = response.get_data(as_text=True)
        self.assertIn('Password must be at least 6 characters long.', html)

    # 13. A valid reset updates the correct database record
    def test_13_valid_reset_updates_database_record(self):
        _, raw_token = PasswordResetToken.create_for_user(self.user1)
        db.session.commit()
        old_hash = self.user1.password_hash

        response = self.client.post(
            f'/auth/reset-password/{raw_token}',
            data={'password': 'SuperNewPassword789', 'confirm_password': 'SuperNewPassword789'},
            follow_redirects=False
        )
        # Should redirect to login page
        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/login', response.headers.get('Location', ''))

        updated_user = db.session.get(User, self.user1.id)
        self.assertNotEqual(updated_user.password_hash, old_hash)
        self.assertTrue(updated_user.check_password('SuperNewPassword789'))

    # 14. The password is stored as a secure hash, never plain text
    def test_14_password_stored_as_secure_hash(self):
        _, raw_token = PasswordResetToken.create_for_user(self.user1)
        db.session.commit()
        new_pwd = 'SecurePassword2026!'

        self.client.post(
            f'/auth/reset-password/{raw_token}',
            data={'password': new_pwd, 'confirm_password': new_pwd},
            follow_redirects=True
        )

        user_db = db.session.get(User, self.user1.id)
        self.assertNotEqual(user_db.password_hash, new_pwd)
        self.assertNotIn(new_pwd, user_db.password_hash)
        self.assertTrue(
            user_db.password_hash.startswith(('scrypt:', 'pbkdf2:sha256:', 'pbkdf2:'))
        )
        self.assertTrue(check_password_hash(user_db.password_hash, new_pwd))

    # 15. The old password fails after a successful reset
    def test_15_old_password_fails_after_reset(self):
        _, raw_token = PasswordResetToken.create_for_user(self.user1)
        db.session.commit()

        self.client.post(
            f'/auth/reset-password/{raw_token}',
            data={'password': 'MyFreshPassword99', 'confirm_password': 'MyFreshPassword99'},
            follow_redirects=True
        )

        # Attempt login with old password
        login_resp = self.client.post(
            '/auth/login',
            data={'username': 'user@example.com', 'password': 'oldPassword123'},
            follow_redirects=True
        )
        self.assertIn('Invalid username/email or password.', login_resp.get_data(as_text=True))

    # 16. The new password works on the existing login page
    def test_16_new_password_works_on_login(self):
        _, raw_token = PasswordResetToken.create_for_user(self.user1)
        db.session.commit()

        self.client.post(
            f'/auth/reset-password/{raw_token}',
            data={'password': 'MyFreshPassword99', 'confirm_password': 'MyFreshPassword99'},
            follow_redirects=True
        )

        # Attempt login with new password
        login_resp = self.client.post(
            '/auth/login',
            data={'username': 'user@example.com', 'password': 'MyFreshPassword99'},
            follow_redirects=True
        )
        self.assertIn('Welcome back, registereduser!', login_resp.get_data(as_text=True))

    # 17. One user's reset token cannot change another user's password
    def test_17_cross_user_isolation(self):
        _, raw_token_user1 = PasswordResetToken.create_for_user(self.user1)
        db.session.commit()

        # User 1 consumes their token to set a new password
        self.client.post(
            f'/auth/reset-password/{raw_token_user1}',
            data={'password': 'UserOneBrandNewPass', 'confirm_password': 'UserOneBrandNewPass'},
            follow_redirects=True
        )

        # User 2 must still have their exact original password
        user2_db = db.session.get(User, self.user2.id)
        self.assertTrue(user2_db.check_password('otherPassword456'))
        self.assertFalse(user2_db.check_password('UserOneBrandNewPass'))

        # User 2 logs in successfully with their existing password
        login_resp2 = self.client.post(
            '/auth/login',
            data={'username': 'otheruser', 'password': 'otherPassword456'},
            follow_redirects=True
        )
        self.assertIn('Welcome back, otheruser!', login_resp2.get_data(as_text=True))

    # 18. Existing users and other application functionality remain intact
    def test_18_existing_functionality_intact(self):
        # Database has users and ingredients
        self.assertEqual(User.query.count(), 2)
        self.assertEqual(Ingredient.query.count(), 1)
        self.assertEqual(Ingredient.query.first().name, 'Citric Acid')

        # Public endpoints still work
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertEqual(self.client.get('/scan').status_code, 200)
        self.assertEqual(self.client.get('/search').status_code, 200)
        self.assertEqual(self.client.get('/forgot-password').status_code, 302)

    # 19. Rate limiting works as expected
    @patch('smtplib.SMTP')
    def test_19_rate_limiting(self, mock_smtp_class):
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        # First request succeeds
        resp1 = self.client.post(
            '/auth/forgot-password',
            data={'email': 'user@example.com'},
            follow_redirects=True
        )
        self.assertIn('Password reset link sent successfully!', resp1.get_data(as_text=True))

        # Immediate second request triggers rate limit cooldown
        resp2 = self.client.post(
            '/auth/forgot-password',
            data={'email': 'user@example.com'},
            follow_redirects=True
        )
        html2 = resp2.get_data(as_text=True)
        self.assertIn('Too many password reset requests.', html2)
        # Ensure second email was not dispatched
        self.assertEqual(mock_server.send_message.call_count, 1)

    # 20. The application starts correctly using its production configuration
    def test_20_production_config_startup(self):
        with patch.dict('os.environ', {'FLASK_ENV': 'production', 'SECRET_KEY': 'prod-test-key-secure-12345'}):
            prod_app = create_app('production')
            self.assertIsNotNone(prod_app)
            self.assertFalse(prod_app.config['DEBUG'])
            self.assertFalse(prod_app.config['TESTING'])
            self.assertEqual(prod_app.config['SECRET_KEY'], 'prod-test-key-secure-12345')
            self.assertIn('smtp.gmail.com', prod_app.config['MAIL_SERVER'])


if __name__ == '__main__':
    unittest.main()
