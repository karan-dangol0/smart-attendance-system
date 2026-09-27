# Smart Attendance AI service

## Web application

The React application supports classes, student face enrollment, CCTV video
uploads, and class-specific attendance.

```bash
cd frontend
npm install
npm run build
cd ..
source .venv/bin/activate
python app_server.py
```

Open <http://127.0.0.1:8000>. Fish shell users can activate Python with
`source .venv/bin/activate.fish` instead.

This service processes a CCTV video without opening a desktop window, recognizes
enrolled people, and stores one attendance record per person per UTC day.

## Enroll people

Create one folder per user and add several clear, front-facing photos. Different
lighting and small pose changes improve matching.

```text
people/
  student-001/
    front.jpg
    left.jpg
  student-002/
    front.jpg
```

The folder name is the stable user ID used in the attendance database.

## Process submitted CCTV footage

```bash
.venv/bin/python attendance_system.py ../sample-videos/c1.mp4
```

For the included sample video, the shorter command also works:

```bash
.venv/bin/python attendance_system.py
```

The command prints newly created attendance records as JSON and stores them in
`data/attendance.db`. Running the same video again on the same day will not
create duplicates.

List everyone recorded as present today:

```bash
.venv/bin/python attendance_system.py --list
```

Useful tuning options:

```bash
.venv/bin/python attendance_system.py video.mp4 \
  --people people --threshold 0.82 --confirmations 3 --sample-every 5
```

- Increase `--threshold` to reduce false matches.
- Increase `--confirmations` to require a person in more sampled frames.
- Reduce `--sample-every` for short or low-frame-rate videos.

## Important production note

The included DCT recognizer is a lightweight baseline for controlled classroom
testing. Before using attendance for consequential decisions, replace it with a
well-evaluated face-embedding model, add liveness/anti-spoofing, obtain consent,
encrypt biometric data, define retention rules, and provide manual correction.
