"""
MangoPoint API — Notification Service
=======================================
Handles email (SMTP) and SMS (Twilio) notifications for alerts.
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List

from ..core.config import settings

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Service for sending alert notifications via email and SMS.
    
    Email: Uses SMTP (configured for Gmail by default)
    SMS: Twilio integration stub (ready for implementation)
    """
    
    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_FROM_EMAIL
        
        self.twilio_sid = settings.TWILIO_ACCOUNT_SID
        self.twilio_token = settings.TWILIO_AUTH_TOKEN
        self.twilio_phone = settings.TWILIO_PHONE_NUMBER
    
    async def send_email_alert(
        self,
        subject: str,
        message: str,
        alert_id: str,
        recipients: Optional[List[str]] = None,
    ) -> bool:
        """
        Send email notification for an alert.
        
        Parameters
        ----------
        subject : str
            Email subject line
        message : str
            Alert message body
        alert_id : str
            Alert identifier for tracking
        recipients : list[str], optional
            Email recipients (defaults to admin email if not provided)
            
        Returns
        -------
        bool
            True if email was sent successfully
        """
        if not self.smtp_user or not self.smtp_password:
            logger.warning("SMTP credentials not configured, skipping email notification")
            return False
        
        if not recipients:
            # Default to admin email (same as SMTP user)
            recipients = [self.smtp_user]
        
        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = ", ".join(recipients)
            
            # Plain text version
            text_body = f"""
MangoPoint Pest Risk Alert
==========================

Alert ID: {alert_id}

{message}

---
This is an automated alert from the MangoPoint pest monitoring system.
"""
            
            # HTML version
            html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .alert-box {{ 
            border: 2px solid #e74c3c; 
            border-radius: 8px; 
            padding: 20px; 
            background-color: #fdf2f2;
        }}
        .alert-header {{ 
            color: #e74c3c; 
            font-size: 24px; 
            font-weight: bold;
            margin-bottom: 15px;
        }}
        .alert-id {{ 
            color: #666; 
            font-size: 12px; 
            margin-bottom: 10px;
        }}
        .message {{ 
            font-size: 16px; 
            line-height: 1.6;
        }}
        .footer {{ 
            margin-top: 20px; 
            padding-top: 10px; 
            border-top: 1px solid #ddd; 
            font-size: 12px; 
            color: #888;
        }}
    </style>
</head>
<body>
    <div class="alert-box">
        <div class="alert-header">🚨 Pest Risk Alert</div>
        <div class="alert-id">Alert ID: {alert_id}</div>
        <div class="message">{message}</div>
    </div>
    <div class="footer">
        This is an automated alert from the MangoPoint pest monitoring system.
    </div>
</body>
</html>
"""
            
            msg.attach(MIMEText(text_body, "plain"))
            msg.attach(MIMEText(html_body, "html"))
            
            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.from_email, recipients, msg.as_string())
            
            logger.info(f"Email alert sent to {recipients} for alert {alert_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
            return False
    
    async def send_sms_alert(
        self,
        message: str,
        alert_id: str,
        recipients: Optional[List[str]] = None,
    ) -> bool:
        """
        Send SMS notification for an alert using Twilio.
        
        This is a Twilio-ready stub. To enable:
        1. Install twilio package
        2. Configure TWILIO_* environment variables
        3. Uncomment the implementation
        
        Parameters
        ----------
        message : str
            SMS message (limited to 160 characters)
        alert_id : str
            Alert identifier for tracking
        recipients : list[str], optional
            Phone numbers to send to
            
        Returns
        -------
        bool
            True if SMS was sent successfully
        """
        if not self.twilio_sid or not self.twilio_token:
            logger.warning("Twilio credentials not configured, skipping SMS notification")
            return False
        
        if not recipients:
            logger.warning("No SMS recipients configured")
            return False
        
        try:
            # Twilio implementation (uncomment when ready)
            # from twilio.rest import Client
            # client = Client(self.twilio_sid, self.twilio_token)
            #
            # for recipient in recipients:
            #     client.messages.create(
            #         body=message[:160],
            #         from_=self.twilio_phone,
            #         to=recipient,
            #     )
            
            # For now, just log the intended SMS
            logger.info(
                f"[SMS STUB] Would send to {recipients}: {message[:50]}... "
                f"(alert: {alert_id})"
            )
            return False  # Return False since we didn't actually send
            
        except Exception as e:
            logger.error(f"Failed to send SMS alert: {e}")
            return False
    
    async def test_email_connection(self) -> bool:
        """Test SMTP connection."""
        if not self.smtp_user or not self.smtp_password:
            return False
        
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
            return True
        except Exception as e:
            logger.error(f"SMTP connection test failed: {e}")
            return False


# Singleton instance
notification_service = NotificationService()
