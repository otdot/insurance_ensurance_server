from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import os
import sqlite3
import sys

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

Path(app.instance_path).mkdir(parents=True, exist_ok=True)
DATABASE_PATH = Path(app.instance_path) / "insurance.db"

# Create both tables up front so GET /works on a virgin database
# (previously GET /products 500'd before the first POST).
with closing(sqlite3.connect(DATABASE_PATH)) as _conn:
    with _conn:
        _conn.execute(
            """
            CREATE TABLE IF NOT EXISTS contracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                pdf_data BLOB NOT NULL,
                uploaded_at TEXT NOT NULL
            )
            """
        )
        _conn.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_name TEXT NOT NULL,
                description TEXT NOT NULL,
                value INTEGER NOT NULL
            )
            """
        )

def _find_harness_dir():
    candidates = [os.environ.get("HARNESS_DIR"),
                  str(Path(__file__).resolve().parent.parent / "harness"),
                  "/home/link/Projects/insuranceensurance/harness"]
    for cand in candidates:
        if cand and (Path(cand) / "initial.py").is_file():
            return cand
    return None

HARNESS_DIR = _find_harness_dir()
harness = None
if HARNESS_DIR:
    sys.path.insert(0, HARNESS_DIR)
    try:
        import initial as harness  # the document/memory engine
    except ImportError as _exc:
        print(f"harness unavailable (install deps from requirements.txt): {_exc}")

@app.route("/", defaults={"filename": "index.html"})
@app.route("/<path:filename>")
def serve_static(filename):
    return send_from_directory(app.static_folder, filename)


@app.errorhandler(404)
def spa_fallback(err):
    """Vue Router uses history mode: /upload etc. are client-side routes,
    not files. Any non-API 404 serves the SPA shell instead of erroring."""
    if app.static_folder and not request.path.startswith(("/api/", "/health", "/products")):
        return send_from_directory(app.static_folder, "index.html")
    return err


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


@app.route("/api/ask", methods=["POST"])
def api_ask():
    """Answer a user question from the stored contracts via the harness:
    extraction, RAG index and concise answers are persisted in harness/.cache,
    keyed to the contract-store revision (auto-invalidates on new uploads).
    Body: {"question", "model"?: OpenRouter model id, "api_key"?: OpenRouter key}
    """
    if harness is None:
        return jsonify(error="harness unavailable (install deps / set HARNESS_DIR)"), 503
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    if len(question) < 3:
        return jsonify(error="Provide a 'question' in the JSON body."), 400
    kwargs = {}
    if data.get("api_key"):
        kwargs["api_key"] = data["api_key"]
    try:
        result = harness.ask_cached(
            question,
            model=data.get("model", "auto"),
            db_path=str(DATABASE_PATH),
            **kwargs,
        )
        return jsonify(result), 200
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except Exception as exc:
        return jsonify(error=f"Harness error: {exc}"), 502


@app.route('/api/products', methods=['POST'])
def create_product():
    data = request.get_json(silent=True)
    
    if not isinstance(data, dict):
        return jsonify(error="JSON object body is required"), 400

    if not data.get("product_name"):
        return jsonify(error="'product_name' is required"), 400
    if data.get("desc") is None:
        return jsonify(error="'desc' is required"), 400
    if data.get("value") is None:
        return jsonify(error="'value' is required"), 400
 
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
