
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

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
INSTANCE_DIR.mkdir(exist_ok=True)

app = Flask(__name__, instance_path=str(INSTANCE_DIR))

app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "local-development-key-change-before-deployment"
)

app.config["MAX_CONTENT_LENGTH"] = 16 * 1024  # 16 KB
CSRFProtect(app)

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


@app.route("/contact", methods=["POST"])
def contact():
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

    flash("Thank you! Your message has been sent successfully.", "success")
    return redirect(url_for("home") + "#contact")


if __name__ == "__main__":
    app.run(debug=True)

