from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from flask import Flask, jsonify, request
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

Path(app.instance_path).mkdir(parents=True, exist_ok=True)
DATABASE_PATH = Path(app.instance_path) / "insurance.db"

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


@app.route('/api/products', methods=['POST'])
def create_product():
    data = request.get_json(silent=True)
    if not data or not data.get("product_name"):
        return jsonify(error="JSON body with a 'name' field is required"), 400
 
    with closing(sqlite3.connect(DATABASE_PATH)) as connection:
        with connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    value INTEGER NOT NULL
                )
                """
            )
            cursor = connection.execute(
                """
                INSERT INTO products (product_name, description, value)
                VALUES (?, ?, ?)
                """, (data.get("product_name"), data.get("desc"), data.get("value"))
            )
            product_id = cursor.lastrowid
    
    return jsonify(
        id=product_id,
        product_name=data.get("product_name"),
        description=data.get("desc"),), 201

@app.get("/products")
def list_items():
    with closing(sqlite3.connect(DATABASE_PATH)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute("SELECT * FROM products ORDER BY id").fetchall()
    return jsonify([dict(r) for r in rows])
 
 
@app.get("/products/<int:item_id>")
def get_item(item_id):
    with closing(sqlite3.connect(DATABASE_PATH)) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute("SELECT * FROM products WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            return jsonify(error="product not found"), 404
    return jsonify(dict(row))

if __name__ == '__main__':
    app.run(debug=True)
