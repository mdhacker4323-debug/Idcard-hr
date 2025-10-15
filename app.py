from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Dict, List

import requests
from flask import Flask, flash, redirect, render_template, request, session, url_for

app = Flask(__name__, template_folder="template")
app.secret_key = "change-this-secret-key"

DATA_FILE = Path(__file__).with_name("data.json")
IMGBB_API_ENDPOINT = "https://api.imgbb.com/1/upload"
IMGBB_API_KEY = "49f51f74c43a4e6d08e5b4a27532acd5"

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}


def _load_entries() -> List[Dict[str, Any]]:
    """Read all entries from the JSON data store."""
    if not DATA_FILE.exists():
        return []

    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
            if isinstance(data, list):
                return data
    except json.JSONDecodeError:
        pass

    # If the file is corrupted or not a list, reset to empty list
    return []


def _save_entry(entry: Dict[str, Any]) -> None:
    """Append a new entry to the JSON data store."""
    entries = _load_entries()
    entries.append(entry)
    with DATA_FILE.open("w", encoding="utf-8") as file:
        json.dump(entries, file, ensure_ascii=False, indent=2)


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _upload_photo_to_imgbb(photo_file) -> tuple[str | None, str | None]:
    """Upload the provided photo to ImgBB and return (url, error_message)."""
    if not _allowed_file(photo_file.filename):
        return None, "Unsupported image format. Please upload PNG, JPG, JPEG, GIF, or WEBP files."

    photo_bytes = photo_file.read()
    if not photo_bytes:
        return None, "Uploaded photo is empty. Please select a valid image."

    encoded_image = base64.b64encode(photo_bytes).decode("utf-8")

    try:
        response = requests.post(
            IMGBB_API_ENDPOINT,
            data={"key": IMGBB_API_KEY, "image": encoded_image},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        return None, f"Unable to upload the photo at the moment. {exc}"

    if not payload.get("success"):
        error_message = payload.get("error", {}).get("message", "Upload failed. Please try again.")
        return None, f"Image upload failed: {error_message}"

    photo_url = payload.get("data", {}).get("url")
    if not photo_url:
        return None, "Could not retrieve the uploaded photo URL from ImgBB."

    return photo_url, None


@app.route("/")
def index() -> str:
    """Render the public form for ID card submissions."""
    return render_template("index.html")


@app.route("/submit", methods=["POST"])
def submit() -> Any:
    """Handle form submissions from the public form."""
    required_fields = [
        "full_name",
        "registration_number",
        "roll_number",
        "session",
        "mobile_number",
        "blood_group",
    ]

    form_data = {field: request.form.get(field, "").strip() for field in required_fields}

    missing_fields = [field for field, value in form_data.items() if not value]
    if missing_fields:
        flash("Please fill in all required fields before submitting.", "danger")
        return redirect(url_for("index"))

    photo_file = request.files.get("photo_file")
    if not photo_file or photo_file.filename.strip() == "":
        flash("Please upload a photo for your ID card.", "danger")
        return redirect(url_for("index"))

    photo_url, error_message = _upload_photo_to_imgbb(photo_file)
    if error_message:
        flash(error_message, "danger")
        return redirect(url_for("index"))

    entry = {**form_data, "photo_url": photo_url}
    _save_entry(entry)

    flash('✅ Submission successful! Your ID card details have been received.'
        , "success")
    return redirect(url_for("index"))


@app.route("/admin", methods=["GET", "POST"])
def admin_panel() -> Any:
    """Display all submitted entries in the admin dashboard.

    The dashboard requires a shared password and stores an auth flag in
    the session to avoid prompting on each request within the same browser
    session.
    """
    if request.method == "POST":
        supplied_password = request.form.get("password", "").strip()
        if supplied_password == "cst2425":
            session["admin_authenticated"] = True
            return redirect(url_for("admin_panel"))

        flash("Incorrect admin password. Please try again.", "danger")
        return redirect(url_for("admin_panel"))

    if not session.get("admin_authenticated"):
        return render_template("admin_login.html")

    entries = _load_entries()
    return render_template("admin.html", entries=entries)


if __name__ == "__main__":
    DATA_FILE.touch(exist_ok=True)
    if DATA_FILE.stat().st_size == 0:
        with DATA_FILE.open("w", encoding="utf-8") as file:
            json.dump([], file)

    app.run(host="0.0.0.0", port=5000, debug=True)