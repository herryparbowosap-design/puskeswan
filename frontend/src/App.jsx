import { useEffect, useState } from "react";

const API = import.meta.env.VITE_API_URL || "";

function api(path, opts = {}) {
  const token = localStorage.getItem("token");
  return fetch(`${API}/api${path}`, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts.headers || {}),
    },
  });
}

function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setErr(null);
    setBusy(true);
    try {
      const r = await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        throw new Error(d.detail || "login gagal");
      }
      const data = await r.json();
      localStorage.setItem("token", data.access_token);
      onLogin(data.user);
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ maxWidth: 360, margin: "12vh auto", padding: 24 }}>
      <h1 style={{ fontWeight: 500, marginBottom: 4 }}>SIM Puskeswan</h1>
      <p style={{ color: "#666", marginTop: 0 }}>Masuk untuk melanjutkan</p>
      <div style={{ display: "grid", gap: 12, marginTop: 20 }}>
        <input
          placeholder="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          style={{ padding: 12, borderRadius: 10, border: "1px solid #ccc", fontSize: 16 }}
        />
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          style={{ padding: 12, borderRadius: 10, border: "1px solid #ccc", fontSize: 16 }}
        />
        {err && <div style={{ color: "#c00", fontSize: 14 }}>{err}</div>}
        <button
          onClick={submit}
          disabled={busy || !username || !password}
          style={{ padding: 12, borderRadius: 10, border: "none", background: "#0f6e56", color: "#fff", fontSize: 16, cursor: "pointer" }}
        >
          {busy ? "Masuk…" : "Masuk"}
        </button>
      </div>
    </div>
  );
}

function Shell({ user, onLogout }) {
  const [role, setRole] = useState(user.roles.length === 1 ? user.roles[0] : null);

  const judul = {
    admin: "Beranda Admin",
    petugas: "Beranda Petugas",
    peternak: "Beranda Peternak",
  };

  if (!role) {
    return (
      <div style={{ maxWidth: 360, margin: "12vh auto", padding: 24 }}>
        <h2 style={{ fontWeight: 500 }}>Halo, {user.nama}</h2>
        <p style={{ color: "#666" }}>Pilih peran:</p>
        <div style={{ display: "grid", gap: 10 }}>
          {user.roles.map((r) => (
            <button
              key={r}
              onClick={() => setRole(r)}
              style={{ padding: 12, borderRadius: 10, border: "1px solid #ccc", fontSize: 16, cursor: "pointer", textTransform: "capitalize" }}
            >
              {r}
            </button>
          ))}
        </div>
        <button onClick={onLogout} style={{ marginTop: 16, background: "none", border: "none", color: "#c00", cursor: "pointer" }}>
          Keluar
        </button>
      </div>
    );
  }

  const desktop = role === "admin";
  return (
    <div style={{ maxWidth: desktop ? 960 : 480, margin: desktop ? "5vh auto" : "8vh auto", padding: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h1 style={{ fontWeight: 500, margin: 0 }}>{judul[role] || "Beranda"}</h1>
          <p style={{ color: "#666", margin: "4px 0 0" }}>
            {user.nama} · {role}
            {user.roles.length > 1 && (
              <button onClick={() => setRole(null)} style={{ marginLeft: 8, background: "none", border: "none", color: "#0f6e56", cursor: "pointer" }}>
                ganti peran
              </button>
            )}
          </p>
        </div>
        <button onClick={onLogout} style={{ background: "none", border: "1px solid #ccc", borderRadius: 8, padding: "6px 12px", cursor: "pointer" }}>
          Keluar
        </button>
      </div>
      <div style={{ marginTop: 24, padding: 20, border: "1px dashed #ccc", borderRadius: 12, color: "#888" }}>
        Fitur untuk peran ini menyusul di slice berikutnya.
      </div>
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) {
      setLoading(false);
      return;
    }
    api("/auth/me")
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setUser)
      .catch(() => localStorage.removeItem("token"))
      .finally(() => setLoading(false));
  }, []);

  function logout() {
    localStorage.removeItem("token");
    setUser(null);
  }

  if (loading) return <div style={{ padding: 24, fontFamily: "system-ui" }}>memuat…</div>;

  return (
    <div style={{ fontFamily: "system-ui, sans-serif" }}>
      {user ? <Shell user={user} onLogout={logout} /> : <Login onLogin={setUser} />}
    </div>
  );
}
