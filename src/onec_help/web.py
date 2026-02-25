"""Flask web app for 1C Help viewer."""

import logging
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory

from .tree import build_tree, get_html_content

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder=Path(__file__).resolve().parent.parent.parent / "templates")
app.config["BASE_DIR"] = None


@app.route("/", methods=["GET", "POST"])
def index():
    """Handle directory input and display main page."""
    if request.method == "POST":
        directory = request.form.get("directory")
        if not directory or not Path(directory).is_dir():
            return render_template("index.html", error="Invalid directory path")
        app.config["BASE_DIR"] = directory
        tree_elements = build_tree(directory)
        import json

        return render_template(
            "index.html",
            success=True,
            tree_elements=json.dumps(tree_elements),
        )
    return render_template("index.html")


@app.route("/content/<path:html_path>")
def get_content(html_path: str):
    """Serve HTML content for a given path."""
    try:
        base_dir = app.config["BASE_DIR"]
        if not base_dir:
            return jsonify({"error": "No directory selected"}), 400
        content = get_html_content(html_path, base_dir)
        return jsonify({"content": content})
    except Exception as e:
        logger.error("Error serving content for %s: %s", html_path, e)
        return jsonify({"error": str(e)}), 500


@app.route("/download/<path:file_path>")
def download_file(file_path: str):
    """Download a file from the base directory."""
    base_dir = app.config["BASE_DIR"]
    if not base_dir:
        return jsonify({"error": "No directory selected"}), 400
    return send_from_directory(base_dir, file_path)


@app.route("/ready")
def ready():
    """Health/readiness endpoint for Docker/Kubernetes."""
    return jsonify({"status": "ok"}), 200
