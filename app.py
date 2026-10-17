from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

Path(app.instance_path).mkdir(parents=True, exist_ok=True)
DATABASE_PATH = Path(app.instance_path) / "insurance.db"

@app.route("/", defaults={"filename": "index.html"})
@app.route("/<path:filename>")
def serve_static(filename):
    return send_from_directory(app.static_folder, filename)


@app.route("/health", methods=["GET"])
def health_check():
    return "OK", 200    

@app.route("/api/contracts", methods=["POST"])
def upload_contract():
    uploaded_file = request.files.get("file")
    if uploaded_file is None or not uploaded_file.filename:
        return jsonify(error="Upload a PDF using the 'file' field."), 400

    pdf_data = uploaded_file.read()
    if b"%PDF-" not in pdf_data[:1024]:
        return jsonify(error="The uploaded file does not appear to be a PDF."), 400

    filename = secure_filename(uploaded_file.filename) or "contract.pdf"
    uploaded_at = datetime.now(timezone.utc).isoformat()

    with closing(sqlite3.connect(DATABASE_PATH)) as connection:
        with connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS contracts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    pdf_data BLOB NOT NULL,
                    uploaded_at TEXT NOT NULL
                )
                """
            )
            cursor = connection.execute(
                """
                INSERT INTO contracts (filename, pdf_data, uploaded_at)
                VALUES (?, ?, ?)
                """,
                (filename, sqlite3.Binary(pdf_data), uploaded_at),
            )
            contract_id = cursor.lastrowid

    return jsonify(
        id=contract_id,
        filename=filename,
        uploaded_at=uploaded_at,
    ), 201


@app.errorhandler(413)
def request_too_large(_error):
    return jsonify(error="Request exceeds the 16 MB upload limit."), 413


if __name__ == "__main__":
    app.run(debug=True)