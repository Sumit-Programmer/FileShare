"""
Instant File Sharing (single-file Flask app)
-------------------------------------------------
Features
- Upload a file and get a unique share link.
- Recipient can open the link and download the file.
- Optional expiry (in hours) and one-time download mode.
- 100 MB upload limit by default.

Run
- pip install flask
- python app.py
- Open http://127.0.0.1:5000

Note: For quick LAN sharing, run with: flask run --host 0.0.0.0
"""
from __future__ import annotations
import os
import sqlite3
import secrets
import mimetypes
from datetime import datetime, timedelta, timezone
from typing import Optional

from flask import (
    Flask, request, redirect, url_for, send_file,
    abort, flash, Response
)
from werkzeug.utils import secure_filename

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(APP_ROOT, "uploads")
DB_PATH = os.path.join(APP_ROOT, "files.db")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(16))
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ---------------------------
# DB Helpers
# ---------------------------

def db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

with db_conn() as conn:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            id TEXT PRIMARY KEY,
            stored_name TEXT NOT NULL,
            original_name TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            mime TEXT,
            created_at TEXT NOT NULL,
            expires_at TEXT,
            one_time INTEGER NOT NULL DEFAULT 0,
            downloads INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.commit()

# ---------------------------
# HTML Templates (inline)
# ---------------------------

BASE_CSS = """
:root{--bg:#0b1220;--card:#121a2a;--muted:#7f8ba3;--accent:#4f8cff;--text:#e9eef7;--danger:#ff5a7a}
*{box-sizing:border-box}body{margin:0;font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Arial,sans-serif;background:var(--bg);color:var(--text)}
.container{max-width:860px;margin:40px auto;padding:0 16px}
.card{background:var(--card);border:1px solid #1f2a41;border-radius:16px;box-shadow:0 10px 30px rgba(0,0,0,.25)}
.header{padding:20px 22px;border-bottom:1px solid #1f2a41;display:flex;justify-content:space-between;align-items:center}
.title{font-size:20px;font-weight:700}
.sub{color:var(--muted);font-size:14px}
.content{padding:22px}
.grid{display:grid;gap:14px}
.label{font-size:13px;color:var(--muted)}
.row{display:flex;gap:10px;align-items:center}
.input,select{width:100%;background:#0d1524;border:1px solid #223154;color:var(--text);padding:12px 14px;border-radius:12px}
.file{border:1px dashed #2b3b61;background:#0b1220}
.btn{appearance:none;border:0;background:var(--accent);color:white;padding:12px 16px;border-radius:12px;font-weight:600;cursor:pointer}
.btn.secondary{background:#223154}
.btn.danger{background:var(--danger)}
.meta{display:grid;grid-template-columns:1fr 1fr;gap:10px;color:var(--muted);font-size:14px}
.linkbox{margin-top:12px;padding:12px 14px;background:#0d1524;border:1px solid #223154;border-radius:12px;word-break:break-all}
.center{text-align:center}
.footer{margin-top:18px;color:var(--muted);font-size:12px}
.alert{margin:0 0 14px 0;padding:12px 14px;border-radius:12px;background:#14233e;border:1px solid #233a6c}
.alert.error{background:#2a1420;border-color:#52253a;color:#ffd4df}
.code{font-family:ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace}
"""

INDEX_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <!-- Adding logo -->
  <link rel="icon" type="image/png" href="logo.png">

  <!-- 🔑 SEO Title -->
  <title>FileShare – Instant & Secure File Sharing Online</title>

  <!-- 📜 Description (shows under title in Google results) -->
  <meta name="description" content="FileShare lets you instantly upload, share, and download files with anyone. Fast, secure, and simple file sharing online.">

  <!-- 🏷 Keywords (not as important for Google, but still useful) -->
  <meta name="keywords" content="file share, instant file sharing, send files online, secure file transfer, share files fast">

  <!-- 📱 Social Media Preview -->
  <meta property="og:title" content="FileShare – Instant & Secure File Sharing Online">
  <meta property="og:description" content="Upload, share, and download files instantly with FileShare. Simple, private, and fast file transfers.">
  <meta property="og:type" content="website">
  <meta property="og:image" content="logo.png">

  <!-- 🐦 Twitter Cards -->
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="FileShare – Instant & Secure File Sharing Online">
  <meta name="twitter:description" content="Instant file sharing made simple. Upload and share files securely with FileShare.">
  <meta name="twitter:image" content="logo.png">

  <!-- 🎨 CSS -->
  <style>{BASE_CSS}</style>
</head>
<body>

<div class='container'>
  <div class='card'>
    <div class='header'>
      <div>
        <div class='title'>Instant File Share</div>
        <div class='sub'>Upload a file, get a link. No signup.</div>
      </div>
    </div>
    <div class='content'>
      <form method='post' action='{upload_url}' enctype='multipart/form-data' class='grid'>
        <div>
          <div class='label'>Choose file</div>
          <input class='input file' type='file' name='file' required>
        </div>
        <div class='row'>
          <div style='flex:1'>
            <div class='label'>Expires in (hours, 0 = never)</div>
            <input class='input' type='number' name='expires' min='0' max='168' value='24'>
          </div>
          <div style='width:260px'>
            <div class='label'>Mode</div>
            <select name='mode' class='input'>
              <option value='standard' selected>Standard (multiple downloads)</option>
              <option value='one'>One-time download</option>
            </select>
          </div>
        </div>
        <div class='row'>
          <button class='btn' type='submit'>Upload & Get Link</button>
          <a class='btn secondary' href='{list_url}'>My recent files</a>
        </div>
        <div class='footer'>Max 100 MB per file. Avoid sensitive data for public servers.</div>
      </form>
    </div>
  </div>
</div>
</body></html>
"""

# ...existing code...
DETAIL_HTML = """
<!doctype html>
<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>
<title>File • {fid}</title>
<!-- Adding logo -->
<link rel="icon" type="image/png" href="logo.png">

<style>{BASE_CSS}</style></head>
<body>
<div class='container'>
  <div class='card'>
    <div class='header'>
      <div>
        <div class='title'>{original_name}</div>
        <div class='sub'>Share ID: <span class='code'>{fid}</span></div>
      </div>
      <a href='{home_url}' class='btn secondary'>New upload</a>
    </div>
    <div class='content'>
      {error_block}
      <div class='meta'>
        <div><b>Size</b><br>{size_human}</div>
        <div><b>MIME</b><br>{mime}</div>
        <div><b>Created</b><br>{created_at}</div>
        <div><b>Expires</b><br>{expires_text}</div>
        <div><b>Downloads</b><br>{downloads}</div>
        <div><b>Mode</b><br>{mode_text}</div>
      </div>
      <div class='row' style='margin-top:14px'>
        {download_button}
        <button class='btn secondary' onclick='copyLink()'>Copy Share Link</button>
      </div>
      <div class='linkbox code' id='share'>{share_url}</div>
    </div>
  </div>
</div>
<script>
function copyLink(){{
  const el = document.getElementById('share');
  navigator.clipboard.writeText(el.textContent.trim());
}}
</script>
</body></html>
"""
# ...existing code...

LIST_HTML = """
<!doctype html>
<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Recent Files</title>
<!-- Adding logo -->
<link rel="icon" type="image/png" href="logo.png">

<style>{BASE_CSS}</style></head>
<body>
<div class='container'>
  <div class='card'>
    <div class='header'>
      <div>
        <div class='title'>Recent Files</div>
        <div class='sub'>Newest first • Temporary list (server memory)</div>
      </div>
      <a href='{home_url}' class='btn secondary'>Back</a>
    </div>
    <div class='content'>
      {files_block}
    </div>
  </div>
</div>
</body></html>
"""

# ---------------------------
# Utilities
# ---------------------------

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def to_iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.astimezone(timezone.utc).isoformat() if dt else None

def from_iso(s: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(s) if s else None

def human_size(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    f = float(n)
    while f >= 1024 and i < len(units) - 1:
        f /= 1024
        i += 1
    return f"{f:.2f} {units[i]}"

# ---------------------------
# Routes
# ---------------------------

@app.route("/")
def index():
    html = INDEX_HTML.format(
        upload_url=url_for("upload"),
        list_url=url_for("recent"),
        BASE_CSS=BASE_CSS
    )
    return Response(html, mimetype="text/html")

@app.post("/upload")
def upload():
    f = request.files.get("file")
    if not f or f.filename == "":
        flash("No file selected.")
        return redirect(url_for("index"))

    original_name = secure_filename(f.filename)
    ext = os.path.splitext(original_name)[1]
    fid = secrets.token_urlsafe(8)
    stored_name = f"{fid}{ext}"
    path = os.path.join(UPLOAD_DIR, stored_name)

    f.save(path)
    size_bytes = os.path.getsize(path)
    mime, _ = mimetypes.guess_type(original_name)

    hours = request.form.get("expires", type=int, default=24)
    expires_at: Optional[datetime] = None
    if hours and hours > 0:
        expires_at = utcnow() + timedelta(hours=min(hours, 24*7))

    one_time = 1 if request.form.get("mode") == "one" else 0

    with db_conn() as conn:
        conn.execute(
            """
            INSERT INTO files (id, stored_name, original_name, size_bytes, mime, created_at, expires_at, one_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fid,
                stored_name,
                original_name,
                size_bytes,
                mime,
                to_iso(utcnow()),
                to_iso(expires_at),
                one_time,
            ),
        )
        conn.commit()

    return redirect(url_for("view_file", fid=fid))

@app.get("/f/<fid>")
def view_file(fid: str):
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM files WHERE id=?", (fid,)).fetchone()
    if not row:
        abort(404)

    expires_at = from_iso(row["expires_at"]) if row["expires_at"] else None
    expired = expires_at and utcnow() > expires_at

    if expired:
        _delete_file_record(row)
        error_block = "<div class='alert error'>This file link has expired.</div>"
        downloadable = False
    else:
        error_block = ""
        downloadable = True

    download_button = (
        f"<a class='btn' href='{url_for('download', fid=fid)}'>Download</a>"
        if downloadable else "<button class='btn danger' disabled>Unavailable</button>"
    )

    share_url = request.url_root.strip("/") + url_for("view_file", fid=fid)

    html = DETAIL_HTML.format(
        BASE_CSS=BASE_CSS,
        fid=fid,
        original_name=row["original_name"],
        home_url=url_for("index"),
        size_human=human_size(row["size_bytes"]),
        mime=row["mime"] or "unknown",
        created_at=row["created_at"],
        expires_text=(expires_at.isoformat() if expires_at else "Never"),
        downloads=row["downloads"],
        mode_text="One-time" if row["one_time"] else "Standard",
        download_button=download_button,
        share_url=share_url,
        error_block=error_block
    )
    return Response(html, mimetype="text/html")

@app.get("/d/<fid>")
def download(fid: str):
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM files WHERE id=?", (fid,)).fetchone()
    if not row:
        abort(404)

    expires_at = from_iso(row["expires_at"]) if row["expires_at"] else None
    if expires_at and utcnow() > expires_at:
        _delete_file_record(row)
        abort(410)

    file_path = os.path.join(UPLOAD_DIR, row["stored_name"])
    if not os.path.exists(file_path):
        _delete_row_only(row["id"])
        abort(404)

    with db_conn() as conn:
        conn.execute("UPDATE files SET downloads=downloads+1 WHERE id=?", (fid,))
        conn.commit()

    resp = send_file(
        file_path,
        as_attachment=True,
        download_name=row["original_name"],
        mimetype=row["mime"] or "application/octet-stream",
        conditional=True,
    )

    if row["one_time"]:
        @resp.call_on_close
        def _cleanup():
            try:
                _delete_file_record(row)
            except Exception:
                pass

    return resp

@app.get("/recent")
def recent():
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT id, original_name, size_bytes FROM files ORDER BY created_at DESC LIMIT 20"
        ).fetchall()

    items_html = ""
    for r in rows:
        items_html += f"""
        <div style='padding:12px;border:1px solid #233a6c;border-radius:12px;'>
          <div style='display:flex;justify-content:space-between;gap:12px;align-items:center;'>
            <div>
              <div><b>{r['original_name']}</b></div>
              <div class='sub'>{r['id']} • {human_size(r['size_bytes'])}</div>
            </div>
            <div class='row'>
              <a class='btn' href='{url_for("view_file", fid=r['id'])}'>Open</a>
              <a class='btn secondary' href='{url_for("download", fid=r['id'])}'>Download</a>
            </div>
          </div>
        </div>
        """
    if not items_html:
        items_html = "<div class='alert'>No files yet. Upload one!</div>"

    html = LIST_HTML.format(BASE_CSS=BASE_CSS, home_url=url_for("index"), files_block=items_html)
    return Response(html, mimetype="text/html")

# ---------------------------
# Cleanup helpers
# ---------------------------

def _delete_file_record(row: sqlite3.Row):
    file_path = os.path.join(UPLOAD_DIR, row["stored_name"])
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    finally:
        with db_conn() as conn:
            conn.execute("DELETE FROM files WHERE id=?", (row["id"],))
            conn.commit()

def _delete_row_only(fid: str):
    with db_conn() as conn:
        conn.execute("DELETE FROM files WHERE id=?", (fid,))
        conn.commit()

# ---------------------------
# Error handlers
# ---------------------------

if __name__ == "__main__":
    app.run(debug=True)
