"""Teste manual de envio pelo SendGrid.

Execute a partir da raiz do repositorio:
    python Back/app/modules/notificacoes/TESTE.py
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

load_dotenv(Path(__file__).resolve().parents[4] / "sendgrid.env")

api_key = os.environ.get("SENDGRID_API_KEY")
if not api_key:
    raise RuntimeError(
        "SENDGRID_API_KEY nao encontrada. Verifique o arquivo sendgrid.env."
    )

sender_email = "fiquedeolho1011@gmail.com"
recipient_email = os.environ.get(
    "SENDGRID_TO_EMAIL",
    "arthuramaral2606@gmail.com",
)

message = Mail(
    from_email=sender_email,
    to_emails=recipient_email,
    subject='Sending with Twilio SendGrid is Fun',
    html_content='<strong>and easy to do anywhere, even with Python</strong>')
try:
    sg = SendGridAPIClient(api_key)
    # sg.set_sendgrid_data_residency("eu")
    # uncomment the above line if you are sending mail using a regional EU subuser
    response = sg.send(message)
    print(response.status_code)
    print(response.body)
    print(response.headers)
except Exception as e:
    print(f"Erro ao enviar email: {e}")
    if hasattr(e, "body"):
        print(f"Detalhes do SendGrid: {e.body}")