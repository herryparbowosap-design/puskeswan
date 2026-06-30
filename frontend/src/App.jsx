import { useEffect, useState, useCallback } from "react";

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

async function jget(path) {
  const r = await api(path);
  if (!r.ok) throw new Error(((await r.json().catch(() => ({}))).detail) || `gagal (${r.status})`);
  return r.json();
}
async function jpost(path, body) {
  const r = await api(path, { method: "POST", body: JSON.stringify(body) });
  if (!r.ok) throw new Error(((await r.json().catch(() => ({}))).detail) || `gagal (${r.status})`);
  return r.json();
}

// Upload 1 file ke S3 lewat presigned URL: minta tiket → PUT byte langsung ke S3.
async function uploadFoto(file, prefix) {
  const ct = file.type || "image/jpeg";
  const presign = await jpost("/foto/presign-upload", { prefix, filename: file.name, content_type: ct });
  const put = await fetch(presign.upload_url, { method: "PUT", headers: { "Content-Type": ct }, body: file });
  if (!put.ok) throw new Error(`upload foto gagal (${put.status})`);
  return { key: presign.key, content_type: ct };
}

async function jpatch(path, body) {
  const r = await api(path, { method: "PATCH", body: JSON.stringify(body) });
  if (!r.ok) throw new Error(((await r.json().catch(() => ({}))).detail) || `gagal (${r.status})`);
  return r.json();
}
async function jdel(path) {
  const r = await api(path, { method: "DELETE" });
  if (!r.ok) {
    const e = new Error(((await r.json().catch(() => ({}))).detail) || `gagal (${r.status})`);
    e.status = r.status;
    throw e;
  }
  return r.json();
}

const inp = { padding: 10, borderRadius: 8, border: "1px solid #ccc", fontSize: 15, width: "100%", boxSizing: "border-box" };
const btn = { padding: "10px 14px", borderRadius: 8, border: "none", background: "#0f6e56", color: "#fff", fontSize: 15, cursor: "pointer" };
const btnGhost = { padding: "8px 12px", borderRadius: 8, border: "1px solid #ccc", background: "#fff", fontSize: 14, cursor: "pointer" };
const card = { border: "1px solid #e3e3e0", borderRadius: 12, padding: 16, background: "#fff" };
const STATUS_COLOR = { aktif: "#0f6e56", mati: "#888", dijual: "#b58100", dipotong: "#a33" };

function hitungUmur(tgl) {
  if (!tgl) return "";
  const lahir = new Date(tgl);
  if (isNaN(lahir.getTime())) return "";
  const now = new Date();
  let bulan = (now.getFullYear() - lahir.getFullYear()) * 12 + (now.getMonth() - lahir.getMonth());
  if (now.getDate() < lahir.getDate()) bulan -= 1;
  if (bulan < 0) bulan = 0;
  const th = Math.floor(bulan / 12);
  const bl = bulan % 12;
  if (th <= 0) return `${bl} bln`;
  if (bl === 0) return `${th} th`;
  return `${th} th ${bl} bln`;
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
      const data = await jpost("/auth/login", { username, password });
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
        <input style={inp} placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} />
        <input style={inp} type="password" placeholder="Password" value={password}
          onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submit()} />
        {err && <div style={{ color: "#c00", fontSize: 14 }}>{err}</div>}
        <button style={btn} onClick={submit} disabled={busy || !username || !password}>{busy ? "Masuk…" : "Masuk"}</button>
      </div>
    </div>
  );
}

function WilayahCascade({ value, onChange }) {
  const [kapList, setKapList] = useState([]);
  const [kalList, setKalList] = useState([]);
  const [padList, setPadList] = useState([]);

  useEffect(() => { jget("/wilayah?level=kapanewon").then(setKapList).catch(() => {}); }, []);
  useEffect(() => {
    if (value.kapanewon_id) jget(`/wilayah?parent_id=${value.kapanewon_id}`).then(setKalList).catch(() => setKalList([]));
    else setKalList([]);
  }, [value.kapanewon_id]);
  useEffect(() => {
    if (value.kalurahan_id) jget(`/wilayah?parent_id=${value.kalurahan_id}`).then(setPadList).catch(() => setPadList([]));
    else setPadList([]);
  }, [value.kalurahan_id]);

  return (
    <div style={{ display: "grid", gap: 8 }}>
      <select style={inp} value={value.kapanewon_id || ""}
        onChange={(e) => onChange({ kapanewon_id: e.target.value || null, kalurahan_id: null, padukuhan_id: null })}>
        <option value="">— Kapanewon —</option>
        {kapList.map((w) => <option key={w.id} value={w.id}>{w.nama}</option>)}
      </select>
      <select style={inp} value={value.kalurahan_id || ""} disabled={!value.kapanewon_id}
        onChange={(e) => onChange({ ...value, kalurahan_id: e.target.value || null, padukuhan_id: null })}>
        <option value="">— Kalurahan —</option>
        {kalList.map((w) => <option key={w.id} value={w.id}>{w.nama}</option>)}
      </select>
      <select style={inp} value={value.padukuhan_id || ""} disabled={!value.kalurahan_id}
        onChange={(e) => onChange({ ...value, padukuhan_id: e.target.value || null })}>
        <option value="">{padList.length ? "— Padukuhan —" : "— Padukuhan (belum ada data) —"}</option>
        {padList.map((w) => <option key={w.id} value={w.id}>{w.nama}</option>)}
      </select>
    </div>
  );
}

function PeternakForm({ initial, onSaved, onCancel }) {
  const isEdit = !!initial;
  const [f, setF] = useState({
    nama: initial?.nama || "", kontak: initial?.kontak || "", nik: initial?.nik || "",
    alamat_detail: initial?.alamat_detail || "", catatan: initial?.catatan || "",
  });
  const [wil, setWil] = useState({
    kapanewon_id: initial?.kapanewon_id || null, kalurahan_id: initial?.kalurahan_id || null, padukuhan_id: initial?.padukuhan_id || null,
  });
  const [koord, setKoord] = useState(
    initial?.koordinat ? { lat: initial.koordinat.coordinates[1], lng: initial.koordinat.coordinates[0] } : null
  );
  const [gps, setGps] = useState("");
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  function ambilGPS() {
    if (!navigator.geolocation) { setGps("GPS tidak tersedia"); return; }
    setGps("mengambil…");
    navigator.geolocation.getCurrentPosition(
      (pos) => { setKoord({ lat: pos.coords.latitude, lng: pos.coords.longitude }); setGps(""); },
      () => setGps("gagal ambil lokasi"),
      { enableHighAccuracy: true, timeout: 10000 }
    );
  }

  async function submit() {
    setErr(null);
    setBusy(true);
    try {
      const body = { ...f, ...wil };
      if (!body.nik) delete body.nik;
      if (koord) body.koordinat = koord;
      const p = isEdit ? await jpatch(`/peternak/${initial.id}`, body) : await jpost("/peternak", body);
      onSaved(p);
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ ...card, display: "grid", gap: 10 }}>
      <strong>{isEdit ? "Edit Peternak" : "Tambah Peternak"}</strong>
      <input style={inp} placeholder="Nama *" value={f.nama} onChange={(e) => setF({ ...f, nama: e.target.value })} />
      <input style={inp} placeholder="No. WA / kontak *" value={f.kontak} onChange={(e) => setF({ ...f, kontak: e.target.value })} />
      <input style={inp} placeholder="NIK (opsional)" value={f.nik} onChange={(e) => setF({ ...f, nik: e.target.value })} />
      <WilayahCascade value={wil} onChange={setWil} />
      <input style={inp} placeholder="Alamat detail (RT/RW, patokan)" value={f.alamat_detail} onChange={(e) => setF({ ...f, alamat_detail: e.target.value })} />
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <button type="button" style={btnGhost} onClick={ambilGPS}>📍 Ambil lokasi GPS</button>
        <span style={{ fontSize: 13, color: "#666" }}>
          {koord ? `${koord.lat.toFixed(5)}, ${koord.lng.toFixed(5)}` : gps || "belum diambil"}
        </span>
      </div>
      {err && <div style={{ color: "#c00", fontSize: 14 }}>{err}</div>}
      <div style={{ display: "flex", gap: 8 }}>
        <button style={btn} disabled={busy || !f.nama || !f.kontak} onClick={submit}>{busy ? "Menyimpan…" : (isEdit ? "Simpan perubahan" : "Simpan")}</button>
        <button style={btnGhost} onClick={onCancel}>Batal</button>
      </div>
    </div>
  );
}

function TernakForm({ peternakId, onCreated, onCancel }) {
  const [spesiesList, setSpesiesList] = useState([]);
  const [rasList, setRasList] = useState([]);
  const [f, setF] = useState({ spesies: "", ras_id: "", mode: "individu", eartag: "", jenis_kelamin: "", tgl_lahir: "", jml_deklarasi: "" });
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { jget("/ras/spesies").then(setSpesiesList).catch(() => {}); }, []);
  useEffect(() => {
    if (f.spesies) jget(`/ras?spesies=${encodeURIComponent(f.spesies)}`).then(setRasList).catch(() => setRasList([]));
    else setRasList([]);
  }, [f.spesies]);

  async function submit() {
    setErr(null);
    setBusy(true);
    try {
      const body = { peternak_id: peternakId, spesies: f.spesies, mode: f.mode };
      if (f.ras_id) body.ras_id = f.ras_id;
      if (f.mode === "individu") {
        if (f.eartag) body.eartag = f.eartag;
        if (f.jenis_kelamin) body.jenis_kelamin = f.jenis_kelamin;
        if (f.tgl_lahir) body.tgl_lahir = f.tgl_lahir;
      } else if (f.jml_deklarasi) {
        body.jml_deklarasi = parseInt(f.jml_deklarasi, 10);
      }
      const t = await jpost("/ternak", body);
      onCreated(t);
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ ...card, display: "grid", gap: 10, background: "#fafafa" }}>
      <strong>Tambah Ternak</strong>
      <select style={inp} value={f.spesies} onChange={(e) => setF({ ...f, spesies: e.target.value, ras_id: "" })}>
        <option value="">— Spesies * —</option>
        {spesiesList.map((s) => <option key={s} value={s}>{s}</option>)}
      </select>
      <select style={inp} value={f.ras_id} disabled={!f.spesies} onChange={(e) => setF({ ...f, ras_id: e.target.value })}>
        <option value="">{rasList.length ? "— Ras —" : "— Ras (pilih spesies dulu) —"}</option>
        {rasList.map((r) => <option key={r.id} value={r.id}>{r.nama}</option>)}
      </select>
      <select style={inp} value={f.mode} onChange={(e) => setF({ ...f, mode: e.target.value })}>
        <option value="individu">Individu (per ekor)</option>
        <option value="populasi">Populasi (kelompok)</option>
      </select>
      {f.mode === "individu" ? (
        <>
          <input style={inp} placeholder="Eartag / nomor" value={f.eartag} onChange={(e) => setF({ ...f, eartag: e.target.value })} />
          <select style={inp} value={f.jenis_kelamin} onChange={(e) => setF({ ...f, jenis_kelamin: e.target.value })}>
            <option value="">— Jenis kelamin —</option>
            <option value="betina">Betina</option>
            <option value="jantan">Jantan</option>
          </select>
          <label style={{ fontSize: 13, color: "#666", display: "grid", gap: 4 }}>
            Tanggal lahir (opsional)
            <input style={inp} type="date" value={f.tgl_lahir} onChange={(e) => setF({ ...f, tgl_lahir: e.target.value })} />
          </label>
        </>
      ) : (
        <input style={inp} type="number" placeholder="Jumlah (deklarasi peternak)" value={f.jml_deklarasi} onChange={(e) => setF({ ...f, jml_deklarasi: e.target.value })} />
      )}
      {err && <div style={{ color: "#c00", fontSize: 14 }}>{err}</div>}
      <div style={{ display: "flex", gap: 8 }}>
        <button style={btn} disabled={busy || !f.spesies} onClick={submit}>{busy ? "Menyimpan…" : "Simpan ternak"}</button>
        <button style={btnGhost} onClick={onCancel}>Batal</button>
      </div>
    </div>
  );
}

function TernakList({ peternakId, refreshKey, isAdmin }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    jget(`/ternak?peternak_id=${peternakId}`).then(setItems).catch(() => setItems([])).finally(() => setLoading(false));
  }, [peternakId]);
  useEffect(() => { load(); }, [load, refreshKey]);

  async function mutasi(t, jenis) {
    const label = { jual: "dijual", mati: "mati", potong: "dipotong" }[jenis];
    if (!window.confirm(`Tandai ternak ini ${label}?`)) return;
    try {
      await jpost(`/ternak/${t.id}/mutasi`, { jenis });
      load();
    } catch (e) {
      window.alert(e.message || e);
    }
  }

  async function hapus(t) {
    if (!window.confirm(`Hapus ternak ${t.spesies}${t.eartag ? " " + t.eartag : ""}? Permanen.`)) return;
    try {
      await jdel(`/ternak/${t.id}`);
      load();
    } catch (e) {
      window.alert(e.message || e);
    }
  }

  if (loading) return <div style={{ color: "#888" }}>memuat ternak…</div>;
  if (!items.length) return <div style={{ color: "#888" }}>Belum ada ternak.</div>;

  return (
    <div style={{ display: "grid", gap: 8 }}>
      {items.map((t) => (
        <div key={t.id} style={{ ...card, display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
          <div>
            <div style={{ fontWeight: 500 }}>
              {t.spesies}{t.eartag ? ` · ${t.eartag}` : ""}{t.mode === "populasi" && t.jml_deklarasi ? ` · ${t.jml_deklarasi} ekor` : ""}
            </div>
            <div style={{ fontSize: 13, color: "#666" }}>
              <span style={{ color: STATUS_COLOR[t.status] || "#333", fontWeight: 500 }}>{t.status}</span>
              {t.jenis_kelamin ? ` · ${t.jenis_kelamin}` : ""}
              {t.tgl_lahir ? ` · ${hitungUmur(t.tgl_lahir)}` : ""}
            </div>
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {t.status === "aktif" && (
              <>
                <button style={btnGhost} onClick={() => mutasi(t, "jual")}>Jual</button>
                <button style={btnGhost} onClick={() => mutasi(t, "mati")}>Mati</button>
                <button style={btnGhost} onClick={() => mutasi(t, "potong")}>Potong</button>
              </>
            )}
            {isAdmin && <button style={{ ...btnGhost, color: "#c00", borderColor: "#e0b4b4" }} onClick={() => hapus(t)}>Hapus</button>}
          </div>
        </div>
      ))}
    </div>
  );
}

function PenyakitPicker({ value, onChange }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!q || q.length < 2) { setResults([]); return; }
    const id = setTimeout(() => {
      jget(`/penyakit?q=${encodeURIComponent(q)}`).then(setResults).catch(() => setResults([]));
    }, 250);
    return () => clearTimeout(id);
  }, [q]);

  if (value) {
    return (
      <div style={{ ...card, padding: 10, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 14 }}><strong>{value.kode}</strong> — {value.nama}</span>
        <button style={btnGhost} onClick={() => onChange(null)}>ganti</button>
      </div>
    );
  }
  return (
    <div style={{ position: "relative" }}>
      <input style={inp} placeholder="Cari kode iSIKHNAS (mis. ovari, ND)…" value={q}
        onChange={(e) => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)} />
      {open && results.length > 0 && (
        <div style={{ position: "absolute", zIndex: 10, background: "#fff", border: "1px solid #ccc", borderRadius: 8, width: "100%", maxHeight: 220, overflowY: "auto", marginTop: 4, boxSizing: "border-box" }}>
          {results.map((r) => (
            <div key={r.kode} style={{ padding: 8, cursor: "pointer", borderBottom: "1px solid #f0f0f0", fontSize: 14 }}
              onClick={() => { onChange({ penyakit_id: r.kode, kode: r.kode, nama: r.nama }); setQ(""); setOpen(false); }}>
              <strong>{r.kode}</strong> — {r.nama} <span style={{ color: "#999", fontSize: 12 }}>({r.kategori})</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function PelayananForm({ peternak, onCreated, onCancel }) {
  const [f, setF] = useState({
    tgl: new Date().toISOString().slice(0, 10), jenis_hewan: "", jumlah: 1,
    diagnosa_teks: "", tindakan: "", prognosa: "", metode_layanan: "Kunjungan Lapangan", keterangan: "",
  });
  const [penyakit, setPenyakit] = useState(null);
  const [foto, setFoto] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [aiTeks, setAiTeks] = useState("");
  const [aiBusy, setAiBusy] = useState(false);
  const [usulan, setUsulan] = useState([]);

  async function runAI() {
    if (aiTeks.trim().length < 5) { setErr("Tulis catatan lapangan dulu untuk dianalisa AI."); return; }
    setErr(null);
    setAiBusy(true);
    try {
      const r = await jpost("/ai/saran", { teks: aiTeks, jenis_hewan: f.jenis_hewan || undefined });
      setF((prev) => ({
        ...prev,
        diagnosa_teks: r.diagnosa_teks || prev.diagnosa_teks,
        tindakan: r.tindakan || prev.tindakan,
        prognosa: r.prognosa || prev.prognosa,
      }));
      setUsulan(r.usulan_kode || []);
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setAiBusy(false);
    }
  }

  async function onPickFoto(e) {
    const files = Array.from(e.target.files || []);
    e.target.value = "";
    if (!files.length) return;
    setErr(null);
    setUploading(true);
    try {
      for (const file of files) {
        const up = await uploadFoto(file, "pelayanan/baru");
        setFoto((prev) => [...prev, { ...up, preview: URL.createObjectURL(file) }]);
      }
    } catch (e2) {
      setErr(String(e2.message || e2));
    } finally {
      setUploading(false);
    }
  }

  async function submit() {
    setErr(null);
    setBusy(true);
    try {
      const body = { kategori: "KESWAN", peternak_id: peternak.id };
      if (f.tgl) body.tgl = f.tgl;
      if (f.diagnosa_teks) body.diagnosa_teks = f.diagnosa_teks;
      if (penyakit) body.penyakit_id = penyakit.penyakit_id;
      if (f.tindakan) body.tindakan = f.tindakan;
      if (f.prognosa) body.prognosa = f.prognosa;
      if (f.metode_layanan) body.metode_layanan = f.metode_layanan;
      if (f.keterangan) body.keterangan = f.keterangan;
      if (f.jenis_hewan) body.hewan = { jenis_hewan: f.jenis_hewan, jumlah: parseInt(f.jumlah, 10) || 1 };
      if (foto.length) body.foto = foto.map((x) => ({ key: x.key, content_type: x.content_type }));
      const rec = await jpost("/pelayanan", body);
      onCreated(rec);
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ ...card, display: "grid", gap: 10, background: "#fafafa" }}>
      <strong>Catat Pelayanan (KESWAN)</strong>
      <input style={inp} type="date" value={f.tgl} onChange={(e) => setF({ ...f, tgl: e.target.value })} />
      <div style={{ display: "flex", gap: 8 }}>
        <input style={inp} placeholder="Jenis hewan (mis. Sapi PFH)" value={f.jenis_hewan} onChange={(e) => setF({ ...f, jenis_hewan: e.target.value })} />
        <input style={{ ...inp, width: 90 }} type="number" min="1" placeholder="Jml" value={f.jumlah} onChange={(e) => setF({ ...f, jumlah: e.target.value })} />
      </div>

      <div style={{ border: "1px dashed #d6a700", borderRadius: 10, padding: 12, background: "#fffdf5", display: "grid", gap: 8 }}>
        <div style={{ fontSize: 13, color: "#9a7b00", fontWeight: 500 }}>✨ Bantuan AI (opsional)</div>
        <textarea style={{ ...inp, minHeight: 60, fontFamily: "inherit" }} value={aiTeks} onChange={(e) => setAiTeks(e.target.value)}
          placeholder="Tulis catatan lapangan bebas… (mis. 'sapi perah ambing bengkak merah, susu menggumpal, nafsu makan turun')" />
        <button type="button" style={{ ...btnGhost, borderColor: "#d6a700", color: "#9a7b00" }} disabled={aiBusy} onClick={runAI}>
          {aiBusy ? "Menganalisa…" : "Analisa dengan AI"}
        </button>
        {usulan.length > 0 && (
          <div style={{ display: "grid", gap: 6 }}>
            <div style={{ fontSize: 12, color: "#666" }}>Usulan kode iSIKHNAS (klik untuk pakai) — periksa dulu:</div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {usulan.map((u) => (
                <button key={u.kode} type="button" title={u.alasan} onClick={() => setPenyakit({ penyakit_id: u.kode, kode: u.kode, nama: u.nama })}
                  style={{ ...btnGhost, fontSize: 13, borderColor: "#0f6e56", color: "#0f6e56" }}>
                  {u.kode} — {u.nama}
                </button>
              ))}
            </div>
          </div>
        )}
        <div style={{ fontSize: 11, color: "#999" }}>AI hanya membantu menyusun; Anda tetap memeriksa &amp; mengonfirmasi sebelum simpan.</div>
      </div>

      <textarea style={{ ...inp, minHeight: 60, fontFamily: "inherit" }} placeholder="Keluhan / diagnosa (teks)" value={f.diagnosa_teks} onChange={(e) => setF({ ...f, diagnosa_teks: e.target.value })} />
      <div>
        <div style={{ fontSize: 13, color: "#666", marginBottom: 4 }}>Kode iSIKHNAS (opsional)</div>
        <PenyakitPicker value={penyakit} onChange={setPenyakit} />
      </div>
      <textarea style={{ ...inp, minHeight: 50, fontFamily: "inherit" }} placeholder="Tindakan / pengobatan" value={f.tindakan} onChange={(e) => setF({ ...f, tindakan: e.target.value })} />
      <div style={{ display: "flex", gap: 8 }}>
        <select style={inp} value={f.prognosa} onChange={(e) => setF({ ...f, prognosa: e.target.value })}>
          <option value="">— Prognosa —</option>
          <option>Fausta</option><option>Dubius</option><option>Infausta</option>
        </select>
        <select style={inp} value={f.metode_layanan} onChange={(e) => setF({ ...f, metode_layanan: e.target.value })}>
          <option value="">— Metode —</option>
          <option>Langsung</option><option>Tidak Langsung</option><option>Telepon/WA</option><option>Kunjungan Lapangan</option>
        </select>
      </div>
      <input style={inp} placeholder="Keterangan (opsional)" value={f.keterangan} onChange={(e) => setF({ ...f, keterangan: e.target.value })} />

      <div>
        <div style={{ fontSize: 13, color: "#666", marginBottom: 6 }}>Foto kasus (opsional)</div>
        {foto.length > 0 && (
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
            {foto.map((x, i) => (
              <div key={x.key} style={{ position: "relative" }}>
                <img src={x.preview} alt="" style={{ width: 64, height: 64, objectFit: "cover", borderRadius: 8, border: "1px solid #ddd" }} />
                <button type="button" onClick={() => setFoto((p) => p.filter((_, j) => j !== i))}
                  style={{ position: "absolute", top: -6, right: -6, width: 20, height: 20, borderRadius: "50%", border: "none", background: "#c00", color: "#fff", cursor: "pointer", fontSize: 12, lineHeight: "20px", padding: 0 }}>×</button>
              </div>
            ))}
          </div>
        )}
        <label style={{ ...btnGhost, display: "inline-block" }}>
          {uploading ? "Mengunggah…" : "📷 Tambah foto"}
          <input type="file" accept="image/*" multiple style={{ display: "none" }} onChange={onPickFoto} disabled={uploading} />
        </label>
      </div>

      {err && <div style={{ color: "#c00", fontSize: 14 }}>{err}</div>}
      <div style={{ display: "flex", gap: 8 }}>
        <button style={btn} disabled={busy || uploading} onClick={submit}>{busy ? "Menyimpan…" : "Simpan pelayanan"}</button>
        <button style={btnGhost} onClick={onCancel}>Batal</button>
      </div>
    </div>
  );
}

function FotoThumb({ fotoKey }) {
  const [url, setUrl] = useState(null);
  useEffect(() => {
    jget(`/foto/url?key=${encodeURIComponent(fotoKey)}`).then((d) => setUrl(d.url)).catch(() => {});
  }, [fotoKey]);
  if (!url) return <div style={{ width: 56, height: 56, borderRadius: 8, background: "#eee" }} />;
  return (
    <a href={url} target="_blank" rel="noreferrer">
      <img src={url} alt="" style={{ width: 56, height: 56, objectFit: "cover", borderRadius: 8, border: "1px solid #ddd" }} />
    </a>
  );
}

function PelayananList({ peternakId, refreshKey, isAdmin }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    jget(`/pelayanan?peternak_id=${peternakId}`).then(setItems).catch(() => setItems([])).finally(() => setLoading(false));
  }, [peternakId]);
  useEffect(() => { load(); }, [load, refreshKey]);

  async function hapus(p) {
    if (!window.confirm(`Hapus pelayanan ${p.tgl}${p.penyakit_id ? " (" + p.penyakit_id + ")" : ""}? Permanen.`)) return;
    try {
      await jdel(`/pelayanan/${p.id}`);
      load();
    } catch (e) {
      window.alert(e.message || e);
    }
  }

  if (loading) return <div style={{ color: "#888" }}>memuat riwayat…</div>;
  if (!items.length) return <div style={{ color: "#888" }}>Belum ada pelayanan tercatat.</div>;

  return (
    <div style={{ display: "grid", gap: 8 }}>
      {items.map((p) => (
        <div key={p.id} style={card}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
            <strong style={{ fontSize: 14 }}>{p.tgl} · {p.kategori}</strong>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {p.penyakit_id && <span style={{ fontSize: 13, color: "#0f6e56" }}>iSIKHNAS: {p.penyakit_id}</span>}
              {isAdmin && <button style={{ ...btnGhost, padding: "2px 8px", fontSize: 12, color: "#c00", borderColor: "#e0b4b4" }} onClick={() => hapus(p)}>Hapus</button>}
            </div>
          </div>
          {p.hewan && <div style={{ fontSize: 13, color: "#666" }}>{p.hewan.jenis_hewan} · {p.hewan.jumlah} ekor</div>}
          {p.diagnosa_teks && <div style={{ fontSize: 14, marginTop: 4 }}>Dx: {p.diagnosa_teks}</div>}
          {p.tindakan && <div style={{ fontSize: 14 }}>Tx: {p.tindakan}</div>}
          {p.foto && p.foto.length > 0 && (
            <div style={{ display: "flex", gap: 6, marginTop: 6, flexWrap: "wrap" }}>
              {p.foto.map((x) => <FotoThumb key={x.key} fotoKey={x.key} />)}
            </div>
          )}
          {(p.prognosa || p.metode_layanan) && (
            <div style={{ fontSize: 12, color: "#999", marginTop: 4 }}>{[p.prognosa, p.metode_layanan].filter(Boolean).join(" · ")}</div>
          )}
        </div>
      ))}
    </div>
  );
}

function PeternakDetail({ peternak, isAdmin, onBack, onUpdated }) {
  const [showForm, setShowForm] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [showPel, setShowPel] = useState(false);
  const [pelKey, setPelKey] = useState(0);
  const [editing, setEditing] = useState(false);
  const [pet, setPet] = useState(peternak);

  async function hapusPeternak() {
    if (!window.confirm(`Hapus peternak "${pet.nama}"? Tindakan ini permanen.`)) return;
    try {
      await jdel(`/peternak/${pet.id}`);
      onUpdated && onUpdated();
      onBack();
    } catch (e) {
      if (e.status === 409) {
        if (window.confirm(`${e.message}\n\nHapus PAKSA peternak ini beserta SEMUA ternak & pelayanannya?`)) {
          try {
            await jdel(`/peternak/${pet.id}?cascade=true`);
            onUpdated && onUpdated();
            onBack();
          } catch (e2) {
            window.alert(e2.message || e2);
          }
        }
      } else {
        window.alert(e.message || e);
      }
    }
  }

  if (editing) {
    return (
      <div style={{ display: "grid", gap: 14 }}>
        <button style={btnGhost} onClick={() => setEditing(false)}>← Batal edit</button>
        <PeternakForm initial={pet} onCancel={() => setEditing(false)}
          onSaved={(p) => { setPet(p); setEditing(false); onUpdated && onUpdated(); }} />
      </div>
    );
  }

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <button style={btnGhost} onClick={onBack}>← Kembali ke daftar</button>
      <div style={card}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
          <div>
            <h2 style={{ margin: "0 0 4px" }}>{pet.nama}</h2>
            <div style={{ color: "#666", fontSize: 14 }}>{pet.kontak}{pet.nik ? ` · NIK ${pet.nik}` : ""}</div>
            {pet.koordinat && (
              <a style={{ fontSize: 14, color: "#0f6e56" }} target="_blank" rel="noreferrer"
                href={`https://www.google.com/maps/dir/?api=1&destination=${pet.koordinat.coordinates[1]},${pet.koordinat.coordinates[0]}`}>
                📍 Buka rute di Google Maps
              </a>
            )}
          </div>
          <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
            <button style={btnGhost} onClick={() => setEditing(true)}>Edit</button>
            {isAdmin && <button style={{ ...btnGhost, color: "#c00", borderColor: "#e0b4b4" }} onClick={hapusPeternak}>Hapus</button>}
          </div>
        </div>
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <strong>Ternak</strong>
        <button style={btn} onClick={() => setShowForm((s) => !s)}>{showForm ? "Tutup" : "+ Tambah ternak"}</button>
      </div>
      {showForm && <TernakForm peternakId={pet.id} onCancel={() => setShowForm(false)}
        onCreated={() => { setShowForm(false); setRefreshKey((k) => k + 1); }} />}
      <TernakList peternakId={pet.id} refreshKey={refreshKey} isAdmin={isAdmin} />

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 6 }}>
        <strong>Riwayat Pelayanan</strong>
        <button style={btn} onClick={() => setShowPel((s) => !s)}>{showPel ? "Tutup" : "+ Catat pelayanan"}</button>
      </div>
      {showPel && <PelayananForm peternak={pet} onCancel={() => setShowPel(false)}
        onCreated={() => { setShowPel(false); setPelKey((k) => k + 1); }} />}
      <PelayananList peternakId={pet.id} refreshKey={pelKey} isAdmin={isAdmin} />
    </div>
  );
}

function PeternakPage({ isAdmin }) {
  const [q, setQ] = useState("");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [selected, setSelected] = useState(null);

  const load = useCallback((query) => {
    setLoading(true);
    jget(`/peternak${query ? `?q=${encodeURIComponent(query)}` : ""}`).then(setItems).catch(() => setItems([])).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const id = setTimeout(() => load(q), 300);
    return () => clearTimeout(id);
  }, [q, load]);

  if (selected) return <PeternakDetail peternak={selected} isAdmin={isAdmin} onUpdated={() => load(q)} onBack={() => { setSelected(null); load(q); }} />;

  return (
    <div style={{ display: "grid", gap: 12 }}>
      <div style={{ display: "flex", gap: 8 }}>
        <input style={inp} placeholder="Cari peternak (nama/kontak/NIK)…" value={q} onChange={(e) => setQ(e.target.value)} />
        <button style={btn} onClick={() => setShowForm((s) => !s)}>{showForm ? "Tutup" : "+ Peternak"}</button>
      </div>
      {showForm && <PeternakForm onCancel={() => setShowForm(false)} onSaved={(p) => { setShowForm(false); setSelected(p); load(q); }} />}
      {loading ? <div style={{ color: "#888" }}>memuat…</div> : (
        <div style={{ display: "grid", gap: 8 }}>
          {items.length === 0 && <div style={{ color: "#888" }}>Belum ada peternak{q ? " yang cocok" : ""}.</div>}
          {items.map((p) => (
            <div key={p.id} style={{ ...card, cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center" }} onClick={() => setSelected(p)}>
              <div>
                <div style={{ fontWeight: 500 }}>{p.nama}</div>
                <div style={{ fontSize: 13, color: "#666" }}>{p.kontak}</div>
              </div>
              <span style={{ color: "#0f6e56" }}>›</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Shell({ user, onLogout }) {
  const [role, setRole] = useState(user.roles.length === 1 ? user.roles[0] : null);
  const judul = { admin: "Beranda Admin", petugas: "Beranda Petugas", peternak: "Beranda Peternak" };

  if (!role) {
    return (
      <div style={{ maxWidth: 360, margin: "12vh auto", padding: 24 }}>
        <h2 style={{ fontWeight: 500 }}>Halo, {user.nama}</h2>
        <p style={{ color: "#666" }}>Pilih peran:</p>
        <div style={{ display: "grid", gap: 10 }}>
          {user.roles.map((r) => (
            <button key={r} style={{ ...btnGhost, textTransform: "capitalize" }} onClick={() => setRole(r)}>{r}</button>
          ))}
        </div>
        <button onClick={onLogout} style={{ marginTop: 16, background: "none", border: "none", color: "#c00", cursor: "pointer" }}>Keluar</button>
      </div>
    );
  }

  const desktop = role === "admin";
  return (
    <div style={{ maxWidth: desktop ? 880 : 520, margin: desktop ? "4vh auto" : "2vh auto", padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div>
          <h1 style={{ fontWeight: 500, margin: 0, fontSize: 22 }}>{judul[role] || "Beranda"}</h1>
          <p style={{ color: "#666", margin: "2px 0 0", fontSize: 14 }}>
            {user.nama} · {role}
            {user.roles.length > 1 && (
              <button onClick={() => setRole(null)} style={{ marginLeft: 8, background: "none", border: "none", color: "#0f6e56", cursor: "pointer" }}>ganti peran</button>
            )}
          </p>
        </div>
        <button onClick={onLogout} style={btnGhost}>Keluar</button>
      </div>
      {(role === "admin" || role === "petugas") ? (
        <PeternakPage isAdmin={user.roles.includes("admin")} />
      ) : (
        <div style={{ ...card, color: "#888" }}>Beranda peternak menyusul di slice berikutnya.</div>
      )}
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) { setLoading(false); return; }
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
