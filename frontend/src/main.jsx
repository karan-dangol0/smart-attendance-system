import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  BookOpen,
  Camera,
  CheckCircle2,
  Plus,
  Upload,
  Users,
  Video,
} from "lucide-react";
import "./styles.css";

const api = async (url, options) => {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Something went wrong");
  return data;
};
const dataUrl = (file) =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });

function App() {
  const [classes, setClasses] = useState([]);
  const [selected, setSelected] = useState("");
  const [attendance, setAttendance] = useState([]);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const current = useMemo(
    () => classes.find((item) => item.id === selected),
    [classes, selected],
  );
  const roster = useMemo(() => {
    const detected = new Map(
      attendance.map((record) => [record.person_id, record]),
    );
    return (current?.students || []).map((student) => ({
      ...student,
      attendance: detected.get(student.id) || null,
    }));
  }, [current, attendance]);
  const load = async () => {
    const items = await api("/api/classes");
    setClasses(items);
    setSelected((value) => value || items[0]?.id || "");
  };
  const loadAttendance = async (id) =>
    setAttendance(id ? await api(`/api/classes/${id}/attendance`) : []);
  useEffect(() => {
    load().catch((error) => setNotice(error.message));
  }, []);
  useEffect(() => {
    loadAttendance(selected).catch((error) => setNotice(error.message));
  }, [selected]);

  async function createClass(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    try {
      const item = await api("/api/classes", {
        method: "POST",
        body: JSON.stringify({ name: form.get("name") }),
      });
      event.currentTarget.reset();
      await load();
      setSelected(item.id);
      setNotice(`${item.name} created`);
    } catch (error) {
      setNotice(error.message);
    } finally {
      setBusy(false);
    }
  }
  async function addStudent(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const photo = form.get("photo");
    setBusy(true);
    try {
      const student = await api(`/api/classes/${selected}/students`, {
        method: "POST",
        body: JSON.stringify({
          student_id: form.get("student_id"),
          name: form.get("name"),
          filename: photo.name,
          photo: await dataUrl(photo),
        }),
      });
      setClasses((items) =>
        items.map((item) =>
          item.id === selected
            ? {
                ...item,
                student_count: item.student_count + 1,
                students: [...(item.students || []), student].sort((a, b) =>
                  a.name.localeCompare(b.name),
                ),
              }
            : item,
        ),
      );
      event.currentTarget.reset();
      setNotice("Student enrolled successfully");
    } catch (error) {
      setNotice(error.message);
    } finally {
      setBusy(false);
    }
  }
  async function processVideo(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const video = form.get("video");
    setBusy(true);
    setNotice("Processing video — this can take a minute…");
    try {
      const result = await api(`/api/classes/${selected}/process`, {
        method: "POST",
        body: JSON.stringify({
          filename: video.name,
          video: await dataUrl(video),
        }),
      });
      await loadAttendance(selected);
      setNotice(
        result.new_records.length
          ? `${result.new_records.length} new attendance record(s)`
          : "Processed successfully — no new attendance",
      );
    } catch (error) {
      setNotice(error.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app">
      <aside>
        <div className="brand">
          <span>
            <Camera size={22} />
          </span>
          <div>
            VisionRoll<small>SMART ATTENDANCE</small>
          </div>
        </div>
        <p className="eyebrow">YOUR CLASSES</p>
        <nav>
          {classes.map((item) => (
            <button
              className={selected === item.id ? "active" : ""}
              onClick={() => setSelected(item.id)}
              key={item.id}
            >
              <BookOpen size={18} />
              <span>
                {item.name}
                <small>{item.student_count} students</small>
              </span>
            </button>
          ))}
        </nav>
        <form className="new-class" onSubmit={createClass}>
          <input name="name" placeholder="e.g. Class 101" required />
          <button disabled={busy}>
            <Plus size={17} /> Create class
          </button>
        </form>
      </aside>
      <main>
        <header>
          <div>
            <p className="eyebrow">CLASSROOM OVERVIEW</p>
            <h1>{current?.name || "Create your first class"}</h1>
          </div>
          <div className="date">
            {new Date().toLocaleDateString(undefined, {
              weekday: "long",
              month: "long",
              day: "numeric",
            })}
          </div>
        </header>
        {notice && (
          <div className="notice" onClick={() => setNotice("")}>
            {notice}
          </div>
        )}
        {!current ? (
          <section className="empty">
            <BookOpen size={42} />
            <h2>No classes yet</h2>
            <p>Create a class from the left panel to begin.</p>
          </section>
        ) : (
          <>
            <section className="stats">
              <article>
                <Users />
                <div>
                  <strong>{current.student_count}</strong>
                  <span>Enrolled students</span>
                </div>
              </article>
              <article>
                <CheckCircle2 />
                <div>
                  <strong>{attendance.length}</strong>
                  <span>Present today</span>
                </div>
              </article>
              <article>
                <Video />
                <div>
                  <strong>
                    {Math.max(0, current.student_count - attendance.length)}
                  </strong>
                  <span>Not detected</span>
                </div>
              </article>
            </section>
            <div className="grid">
              <section className="card">
                <div className="card-title">
                  <div>
                    <p className="eyebrow">ENROLLMENT</p>
                    <h2>Add a student</h2>
                  </div>
                  <Users />
                </div>
                <form onSubmit={addStudent}>
                  <label>
                    Student name
                    <input name="name" placeholder="Full name" required />
                  </label>
                  <label>
                    Student ID
                    <input
                      name="student_id"
                      placeholder="e.g. STU-001"
                      required
                    />
                  </label>
                  <label className="drop">
                    <Camera />
                    <b>Choose a clear face photo</b>
                    <span>JPG, PNG or WebP</span>
                    <input
                      name="photo"
                      type="file"
                      accept="image/jpeg,image/png,image/webp"
                      required
                    />
                  </label>
                  <button className="primary" disabled={busy}>
                    Enroll student
                  </button>
                </form>
              </section>
              <section className="card accent">
                <div className="card-title">
                  <div>
                    <p className="eyebrow">CCTV PROCESSING</p>
                    <h2>Take attendance</h2>
                  </div>
                  <Video />
                </div>
                <form onSubmit={processVideo}>
                  <label className="drop video">
                    <Upload />
                    <b>Upload classroom footage</b>
                    <span>Choose an MP4 or other OpenCV-supported video</span>
                    <input name="video" type="file" accept="video/*" required />
                  </label>
                  <button className="primary dark" disabled={busy}>
                    {busy ? "Working…" : "Process attendance"}
                  </button>
                </form>
              </section>
            </div>
            <section className="card roster">
              <div className="card-title">
                <div>
                  <p className="eyebrow">TODAY</p>
                  <h2>Attendance roster</h2>
                </div>
                <span className="pill">{attendance.length} present</span>
              </div>
              {roster.length ? (
                <table>
                  <thead>
                    <tr>
                      <th>Student</th>
                      <th>ID</th>
                      <th>Detected at</th>
                      <th>Confidence</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {roster.map((row) => (
                      <tr key={row.id}>
                        <td>
                          <b>{row.name}</b>
                        </td>
                        <td>{row.id}</td>
                        <td>
                          {row.attendance
                            ? new Date(
                                row.attendance.recorded_at,
                              ).toLocaleTimeString()
                            : "—"}
                        </td>
                        <td>
                          {row.attendance
                            ? `${(row.attendance.confidence * 100).toFixed(1)}%`
                            : "—"}
                        </td>
                        <td>
                          <span
                            className={
                              row.attendance ? "present" : "not-detected"
                            }
                          >
                            {row.attendance ? "Present" : "Not detected"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="empty small">
                  <Users />
                  <p>No students enrolled in this class yet.</p>
                </div>
              )}
            </section>
          </>
        )}
      </main>
    </div>
  );
}
createRoot(document.getElementById("root")).render(<App />);
