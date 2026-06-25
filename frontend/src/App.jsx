import { useEffect, useState } from "react";

const API = import.meta.env.VITE_API_URL || "";

export default function App() {
  const [health, setHealth] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    fetch(`${API}/api/health`)
      .then((r) => r.json())
      .then(setHealth)
      .catch((e) => setErr(String(e)));
  }, []);

  return (
    <div style={{ fontFamily: "system-ui, sans-serif", maxWidth: 420, margin: "10vh auto", padding: 24 }}>
      <h1 style={{ fontWeight: 500, marginBottom: 4 }}>SIM Puskeswan</h1>
      <p style={{ color: "#666", marginTop: 0 }}>Administrasi keswan &amp; layanan peternak</p>

      <div style={{ marginTop: 24, padding: 16, border: "1px solid #ddd", borderRadius: 12 }}>
        <strong>Status backend</strong>
        <div style={{ marginTop: 8 }}>
          {err && <span style={{ color: "#c00" }}>gagal terhubung: {err}</span>}
          {!err && !health && <span>memeriksa…</span>}
          {health && <span>ok · mongo: {String(health.mongo)}</span>}
        </div>
      </div>

      {/* Fase 1: login + shell peran (peternak / petugas / admin) */}
    </div>
  );
}
