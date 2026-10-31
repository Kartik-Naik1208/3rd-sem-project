import logging
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from flask import current_app

logger = logging.getLogger(__name__)


class EmailService:
    """Service for dispatching transactional emails using Gmail SMTP."""

    @classmethod
    def send_password_reset_email(cls, to_email: str, username: str, reset_url: str) -> bool:
        """
        Sends a secure password reset email with both plain-text and HTML formats.
        Returns True if the email was successfully dispatched, False otherwise.
        Never logs sensitive credentials or tokens.
        """
        mail_server = current_app.config.get('MAIL_SERVER', 'smtp.gmail.com')
        mail_port = int(current_app.config.get('MAIL_PORT', 587))
        mail_use_tls = current_app.config.get('MAIL_USE_TLS', True)
        mail_username = current_app.config.get('MAIL_USERNAME', '')
        mail_password = current_app.config.get('MAIL_PASSWORD', '')
        default_sender = current_app.config.get(
            'MAIL_DEFAULT_SENDER',
            mail_username or 'noreply@ingredientiq.com'
        )

        current_year = datetime.now(timezone.utc).year

        # Plain text fallback
        plain_body = f"""Hello {username},

We received a request to reset your IngredientIQ account password.

To set a new password, click the link below or copy and paste it into your browser:
{reset_url}

This link is valid for 30 minutes.

If you did not request a password reset, you can safely ignore this email. Your account remains secure and no changes have been made.

Best regards,
The IngredientIQ Team
https://ingredientiq-cymt.onrender.com
"""

        # Branded responsive HTML
        html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Reset Your IngredientIQ Password</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      background-color: #f8f9fa;
      margin: 0;
      padding: 24px;
      color: #212529;
    }}
    .email-container {{
      max-width: 580px;
      margin: 0 auto;
      background-color: #ffffff;
      border-radius: 12px;
      border: 1px solid #e9ecef;
      overflow: hidden;
      box-shadow: 0 4px 12px rgba(0,0,0,0.05);
    }}
    .header {{
      background: linear-gradient(135deg, #198754 0%, #146c43 100%);
      padding: 32px 24px;
      text-align: center;
      color: #ffffff;
    }}
    .brand-title {{
      font-size: 24px;
      font-weight: 700;
      margin: 0;
      letter-spacing: -0.5px;
    }}
    .brand-sub {{
      font-size: 13px;
      color: #d1e7dd;
      margin-top: 4px;
    }}
    .content {{
      padding: 32px 28px;
      line-height: 1.6;
    }}
    .greeting {{
      font-size: 18px;
      font-weight: 600;
      margin-bottom: 16px;
    }}
    .btn-container {{
      text-align: center;
      margin: 32px 0;
    }}
    .btn-primary {{
      background-color: #198754;
      color: #ffffff !important;
      text-decoration: none;
      padding: 14px 32px;
      border-radius: 8px;
      font-weight: 700;
      font-size: 15px;
      display: inline-block;
      box-shadow: 0 2px 6px rgba(25, 135, 84, 0.35);
    }}
    .info-box {{
      background-color: #f1f8f4;
      border-left: 4px solid #198754;
      padding: 12px 16px;
      border-radius: 4px;
      font-size: 13px;
      color: #0f5132;
      margin: 24px 0;
    }}
    .link-fallback {{
      font-size: 12px;
      color: #6c757d;
      word-break: break-all;
      margin-top: 24px;
      padding-top: 16px;
      border-top: 1px solid #dee2e6;
    }}
    .footer {{
      padding: 20px 24px;
      background-color: #f8f9fa;
      border-top: 1px solid #e9ecef;
      text-align: center;
      font-size: 12px;
      color: #6c757d;
    }}
  </style>
</head>
<body>
  <div class="email-container">
    <div class="header">
      <div class="brand-title">&#127793; IngredientIQ</div>
      <div class="brand-sub">Smart Food &amp; Label Safety Scanner</div>
    </div>
    <div class="content">
      <div class="greeting">Hello {username},</div>
      <p>We received a request to reset the password for your IngredientIQ account. Click the button below to create a new password:</p>
      
      <div class="btn-container">
        <a href="{reset_url}" class="btn-primary" target="_blank" rel="noopener noreferrer">Reset Password</a>
      </div>

      <div class="info-box">
        <strong>Note:</strong> This password reset link is valid for <strong>30 minutes</strong> and can only be used once.
      </div>

      <p style="font-size: 13px; color: #6c757d;">
        If you did not request a password reset, you can safely ignore this email. Your current password remains secure and no changes have been made to your account.
      </p>

      <div class="link-fallback">
        If the button above does not work, copy and paste this URL into your browser:<br>
        <a href="{reset_url}" style="color: #198754;">{reset_url}</a>
      </div>
    </div>
    <div class="footer">
      &copy; {current_year} IngredientIQ. All rights reserved.<br>
      Protecting you and your family with ingredient transparency.
    </div>
  </div>
</body>
</html>
"""

        msg = EmailMessage()
        msg['Subject'] = 'Reset Your IngredientIQ Password'
        msg['From'] = default_sender
        msg['To'] = to_email
        msg.set_content(plain_body)
        msg.add_alternative(html_body, subtype='html')

        try:
            with smtplib.SMTP(mail_server, mail_port, timeout=15) as server:
                if mail_use_tls:
                    server.starttls()
                if mail_username and mail_password:
                    server.login(mail_username, mail_password)
                server.send_message(msg)
            logger.info("Password reset email sent successfully to %s", to_email)
            return True
        except Exception as e:
            # Safe logging: logs the exception class and sanitized message without secrets/tokens
            logger.error("Failed to send password reset email via SMTP: %s", type(e).__name__)
            return False
