"""HTTP API and static server for the smart-attendance web application."""

from __future__ import annotations

import base64
import json
import mimetypes
import re
import sqlite3
import tempfile
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from attendance_system import AttendanceStore, process_video


ROOT = Path(__file__).parent
DATA = ROOT / "data"
DATABASE = DATA / "app.db"
FRONTEND = ROOT / "frontend" / "dist"
MAX_UPLOAD = 500 * 1024 * 1024


def connection() -> sqlite3.Connection:
    DATA.mkdir(exist_ok=True)
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS classes (
            id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS students (
            id TEXT NOT NULL, class_id TEXT NOT NULL, name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (class_id, id),
            FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
        );
        """
    )
    return db


def slug(value: str) -> str:
    result = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
    return result or uuid.uuid4().hex[:8]


def decode_data_url(value: str) -> bytes:
    try:
        header, payload = value.split(",", 1)
        if ";base64" not in header:
            raise ValueError
        return base64.b64decode(payload, validate=True)
    except (ValueError, base64.binascii.Error) as error:
        raise ValueError("Invalid uploaded file data") from error


def class_paths(class_id: str) -> tuple[Path, Path]:
    root = DATA / "classes" / class_id
    return root / "people", root / "attendance.db"


class Handler(BaseHTTPRequestHandler):
    server_version = "SmartAttendance/1.0"

    def json_response(self, status: int, payload: object) -> None:
        encoded = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def read_json(self) -> dict:
        size = int(self.headers.get("Content-Length", "0"))
        if size > MAX_UPLOAD:
            raise ValueError("Upload is larger than 500 MB")
        try:
            return json.loads(self.rfile.read(size))
        except json.JSONDecodeError as error:
            raise ValueError("Invalid JSON request") from error

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path == "/api/classes":
                return self.list_classes()
            match = re.fullmatch(r"/api/classes/([^/]+)/attendance", path)
            if match:
                return self.list_attendance(match.group(1))
            self.serve_static(path)
        except Exception as error:
            self.json_response(500, {"error": str(error)})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path == "/api/classes":
                return self.create_class(self.read_json())
            match = re.fullmatch(r"/api/classes/([^/]+)/students", path)
            if match:
                return self.create_student(match.group(1), self.read_json())
            match = re.fullmatch(r"/api/classes/([^/]+)/process", path)
            if match:
                return self.process_attendance(match.group(1), self.read_json())
            self.json_response(404, {"error": "Endpoint not found"})
        except ValueError as error:
            self.json_response(400, {"error": str(error)})
        except sqlite3.IntegrityError as error:
            self.json_response(409, {"error": "That class or student ID already exists"})
        except Exception as error:
            self.json_response(500, {"error": str(error)})

    def list_classes(self) -> None:
        with connection() as db:
            classes = [dict(row) for row in db.execute(
                """SELECT c.id, c.name, c.created_at, COUNT(s.id) student_count
                   FROM classes c LEFT JOIN students s ON s.class_id = c.id
                   GROUP BY c.id ORDER BY c.created_at DESC"""
            )]
            for item in classes:
                item["students"] = [dict(row) for row in db.execute(
                    "SELECT id, name, created_at FROM students WHERE class_id=? ORDER BY name",
                    (item["id"],),
                )]
        self.json_response(200, classes)

    def create_class(self, body: dict) -> None:
        name = str(body.get("name", "")).strip()
        if not name:
            raise ValueError("Class name is required")
        class_id = slug(name)
        now = datetime.now(timezone.utc).isoformat()
        with connection() as db:
            db.execute("INSERT INTO classes VALUES (?, ?, ?)", (class_id, name, now))
        people, _ = class_paths(class_id)
        people.mkdir(parents=True, exist_ok=True)
        self.json_response(201, {"id": class_id, "name": name, "created_at": now})

    def create_student(self, class_id: str, body: dict) -> None:
        student_id = slug(str(body.get("student_id", "")))
        name = str(body.get("name", "")).strip()
        photo = body.get("photo")
        filename = Path(str(body.get("filename", "face.jpg"))).name
        if not name or not body.get("student_id") or not photo:
            raise ValueError("Student ID, name, and face photo are required")
        extension = Path(filename).suffix.lower()
        if extension not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise ValueError("Face photo must be JPG, PNG, or WebP")
        with connection() as db:
            if not db.execute("SELECT 1 FROM classes WHERE id=?", (class_id,)).fetchone():
                raise ValueError("Class does not exist")
            now = datetime.now(timezone.utc).isoformat()
            db.execute(
                "INSERT INTO students VALUES (?, ?, ?, ?)",
                (student_id, class_id, name, now),
            )
        people, _ = class_paths(class_id)
        folder = people / student_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / ("face" + extension)).write_bytes(decode_data_url(photo))
        self.json_response(201, {"id": student_id, "name": name, "created_at": now})

    def process_attendance(self, class_id: str, body: dict) -> None:
        filename = Path(str(body.get("filename", "video.mp4"))).name
        video = body.get("video")
        if not video:
            raise ValueError("CCTV video is required")
        people, attendance_db = class_paths(class_id)
        with connection() as db:
            if not db.execute("SELECT 1 FROM classes WHERE id=?", (class_id,)).fetchone():
                raise ValueError("Class does not exist")
        suffix = Path(filename).suffix or ".mp4"
        with tempfile.NamedTemporaryFile(suffix=suffix, dir=DATA, delete=False) as upload:
            upload.write(decode_data_url(video))
            upload_path = Path(upload.name)
        try:
            records = process_video(
                upload_path, people, attendance_db,
                confirmations=2, sample_every=5,
            )
            # Replace the temporary filename with the original upload name.
            if records:
                store = AttendanceStore(attendance_db)
                store.connection.execute(
                    "UPDATE attendance SET source=? WHERE source=?",
                    (filename, upload_path.name),
                )
                store.connection.commit()
                store.close()
                records = [type(r)(r.person_id, r.recorded_at, r.confidence, filename) for r in records]
        finally:
            upload_path.unlink(missing_ok=True)
        self.json_response(200, {"new_records": [asdict(record) for record in records]})

    def list_attendance(self, class_id: str) -> None:
        _, attendance_db = class_paths(class_id)
        today = datetime.now(timezone.utc).date().isoformat()
        records = []
        if attendance_db.exists():
            store = AttendanceStore(attendance_db)
            records = [asdict(item) for item in store.list_for_date(today)]
            store.close()
        with connection() as db:
            names = {row["id"]: row["name"] for row in db.execute(
                "SELECT id, name FROM students WHERE class_id=?", (class_id,)
            )}
        for record in records:
            record["name"] = names.get(record["person_id"], record["person_id"])
        self.json_response(200, records)

    def serve_static(self, path: str) -> None:
        if not FRONTEND.exists():
            return self.json_response(503, {"error": "Frontend is not built. Run: cd frontend && npm install && npm run build"})
        requested = FRONTEND / (path.lstrip("/") or "index.html")
        try:
            requested.resolve().relative_to(FRONTEND.resolve())
        except ValueError:
            return self.json_response(403, {"error": "Forbidden"})
        if not requested.is_file():
            requested = FRONTEND / "index.html"
        content = requested.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(requested)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


if __name__ == "__main__":
    connection().close()
    print("Smart Attendance running at http://127.0.0.1:8000")
    ThreadingHTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
