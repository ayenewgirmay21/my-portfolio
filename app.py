
import os
import re
import sqlite3
from pathlib import Path

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_wtf.csrf import CSRFProtect
import smtplib
from email.message import EmailMessage

from flask import session
import secrets
from datetime import timedelta
from functools import wraps
from werkzeug.security import check_password_hash


BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
INSTANCE_DIR.mkdir(exist_ok=True)

app = Flask(__name__, instance_path=str(INSTANCE_DIR))

app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "local-development-key-change-before-deployment"
)

app.config["MAX_CONTENT_LENGTH"] = 16 * 1024  # 16 KB
CSRFProtect(app)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=(
        os.environ.get("COOKIE_SECURE", "false").lower() == "true"
    ),
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
)


DATABASE_PATH = Path(
    os.environ.get(
        "DATABASE_PATH",
        str(INSTANCE_DIR / "messages.db"),
    )
)


def initialize_database():
    """Create the contact-message table if it does not exist."""
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


initialize_database()


@app.route("/")
def home():
    certificate_folder = Path(app.static_folder) / "certificates"
    allowed_extensions = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}

    certificates = sorted(
        file.name
        for file in certificate_folder.iterdir()
        if file.is_file() and file.suffix.lower() in allowed_extensions
    ) if certificate_folder.exists() else []

    return render_template("index.html", certificates=certificates)



def send_contact_notification(name, visitor_email, visitor_message):
    import json
    import urllib.request
    import urllib.error

    print("EMAIL NOTIFICATION FUNCTION REACHED")

    api_key = os.environ.get("BREVO_API_KEY", "").strip()
    recipient = os.environ.get("CONTACT_TO_EMAIL", "").strip()
    sender = os.environ.get("GMAIL_SENDER", "").strip()

    if not api_key or not recipient or not sender:
        print("Brevo notification skipped: required environment variables missing.")
        return False

    payload = {
        "sender": {
            "name": "Ayenew - Portfolio",
            "email": sender
        },
        "to": [{"email": recipient}],
        "replyTo": {"email": visitor_email},
        "subject": "New portfolio contact form message",
        "textContent": (
            f"New message from your portfolio website.\n\n"
            f"Name: {name}\n"
            f"Visitor email: {visitor_email}\n\n"
            f"Message:\n{visitor_message}"
        )
    }

    request = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "api-key": api_key,
            "accept": "application/json",
            "content-type": "application/json"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            print("Brevo API response status:", response.status)

        print("Portfolio contact email notification sent via Brevo.")
        return True

    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        print("Brevo email API failed:", exc.code, detail[:1000])
        return False

    except Exception as exc:
        print("Brevo connection failed:", type(exc).__name__, str(exc))
        return False


@app.route("/contact", methods=["POST"])
def contact():
    print("CONTACT ROUTE REACHED")
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    message = request.form.get("message", "").strip()

    if not name or not email or not message:
        flash("Please complete all contact form fields.", "error")
        return redirect(url_for("home") + "#contact")

    if len(name) > 100 or len(email) > 254 or len(message) > 5000:
        flash("Your message is too long. Please shorten it and try again.", "error")
        return redirect(url_for("home") + "#contact")

    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            "INSERT INTO messages (name, email, message) VALUES (?, ?, ?)",
            (name, email, message),
        )

    # Save the message first, then attempt email notification.
    # An email failure will not discard the saved contact message.
    send_contact_notification(name, email, message)

    flash("Thank you! Your message has been sent successfully.", "success")
    return redirect(url_for("home") + "#contact")



def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped_view


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    admin_username = os.environ.get("ADMIN_USERNAME")
    password_hash = os.environ.get("ADMIN_PASSWORD_HASH")

    if not admin_username or not password_hash:
        return "Admin login is not configured.", 503

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        username_ok = secrets.compare_digest(username, admin_username)
        password_ok = check_password_hash(password_hash, password)

        if username_ok and password_ok:
            session.clear()
            session["admin_logged_in"] = True
            session.permanent = True
            return redirect(url_for("admin_inbox"))

        flash("Invalid username or password.", "error")

    return render_template("admin_login.html")


@app.route("/admin", methods=["GET"])
@admin_required
def admin_inbox():
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.row_factory = sqlite3.Row
        messages = connection.execute(
            """
            SELECT id, name, email, message, created_at
            FROM messages
            ORDER BY id DESC
            """
        ).fetchall()

    response = render_template(
        "admin_messages.html",
        messages=messages,
    )
    return response


@app.route("/admin/logout", methods=["POST"])
@admin_required
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


if __name__ == "__main__":
    app.run(debug=True)

