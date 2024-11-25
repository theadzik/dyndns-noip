import logging
import os
import platform
import re
import signal
import smtplib
from base64 import b64encode
from email.message import EmailMessage

import requests


class HandlerDNS:
    def __init__(self, public_ip: str):
        self.username = os.environ["NOIP_USERNAME"]
        self.password = os.environ["NOIP_PASSWORD"]
        self.hostname = os.environ["HOSTNAME"]
        self.public_ip = public_ip
        self.update_url = (
            "https://dynupdate.no-ip.com/nic/update"
            f"?hostname={self.hostname}"
            f"&myip={self.public_ip}"
        )
        self.smtp_username = os.getenv("SMTP_USERNAME", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.smtp_host = os.getenv("SMTP_HOST", "")
        self.smtp_port = int(os.getenv("SMTP_PORT", 465))
        self.notification_email = os.getenv("NOTIFICATION_EMAIL", "")

        self.emails_enabled = all([
            self.smtp_username,
            self.smtp_password,
            self.smtp_host,
            self.smtp_port,
            self.notification_email
        ])

    def get_headers(self) -> dict:
        # encode -> encode -> decode to get string -> bytes -> base64 bytes -> base64 string
        basic_auth = b64encode(f"{self.username}:{self.password}".encode()).decode()
        headers = {
            "Authorization": f"Basic {basic_auth}",
            "User-Agent": f"theadzik/dyndns-noip"
                          f"{platform.system()}{platform.release()}"
                          f"-{os.environ['APP_VERSION']}"
                          f" adam@zmuda.pro"
        }
        return headers

    def update_dns_entry(self) -> bool:
        update = requests.request(
            method="GET",
            url=self.update_url,
            headers=self.get_headers()
        )

        result = self.handle_response(update)
        return result

    def handle_response(self, response: requests.Response) -> bool:
        # https://www.noip.com/integrate/response
        if re.match(r"good.*", response.text):
            logging.info(f"Updated DNS. [{response.status_code}] {response.text}")
            return True
        elif re.match(r"nochg.*", response.text):
            logging.warning(f"No changes. [{response.status_code}] {response.text}")
            return True
        elif re.match(r"nohost|badauth|badagent|!donator|abuse", response.text):
            logging.critical(f"Failed to update DNS: [{response.status_code}] {response.text}")
            if self.emails_enabled:
                self.send_error_email(status_code=response.status_code, response_text=response.text)
            logging.warning("Waiting indefinitely.")
            signal.pause()
        elif re.match(r"911", response.text):
            logging.warning(f"Failed to update DNS: [{response.status_code}] {response.text}")
        else:
            logging.error(f"Did not understand response: [{response.status_code}] {response.text}")
        return False

    def send_error_email(self, status_code: int, response_text: str):
        message = EmailMessage()
        message.set_content(
            f"We failed to update your DNS entries.\n"
            f"Public IP: {self.public_ip}\n"
            f"Response: [{status_code}] {response_text}"
        )
        message['Subject'] = f"[DDNS] Failed to update IP ({response_text})"
        message['From'] = self.smtp_username
        message['To'] = self.notification_email

        mailer = smtplib.SMTP_SSL(host=self.smtp_host, port=self.smtp_port)
        mailer.login(user=self.smtp_username, password=self.smtp_password)
        mailer.send_message(msg=message)
        logging.info(f"Sent an email to {message['To']}")
