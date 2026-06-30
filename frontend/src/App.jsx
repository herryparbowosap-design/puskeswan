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

function hitungDosis(o, beratKg) {
  if (!o || !o.dosis_per_kg || !o.konsentrasi || !beratKg || beratKg <= 0) return null;
  const v = (o.dosis_per_kg * beratKg) / o.konsentrasi;
  return Math.round(v * 100) / 100;
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
    tgl: new Date().toISOString().slice(0, 10), jumlah: 1,
    diagnosa_teks: "", tindakan: "", prognosa: "", metode_layanan: "Kunjungan Lapangan", keterangan: "",
  });
  const [ternakList, setTernakList] = useState([]);
  const [ternakSel, setTernakSel] = useState("");      // id ternak | "lainnya" | ""
  const [jenisManual, setJenisManual] = useState("");
  const [berat, setBerat] = useState("");
  const [obatList, setObatList] = useState([]);
  const [obatSel, setObatSel] = useState("");
  const [obatJml, setObatJml] = useState("");
  const [obatDipakai, setObatDipakai] = useState([]);
  const [penyakit, setPenyakit] = useState(null);
  const [foto, setFoto] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [aiTeks, setAiTeks] = useState("");
  const [aiBusy, setAiBusy] = useState(false);
  const [usulan, setUsulan] = useState([]);

  useEffect(() => {
    jget(`/ternak?peternak_id=${peternak.id}`).then(setTernakList).catch(() => {});
    jget("/obat").then(setObatList).catch(() => {});
  }, [peternak.id]);

  const ternakLabel = (t) =>
    `${t.spesies}${t.eartag ? " · " + t.eartag : ""}` +
    `${t.mode === "populasi" && t.jml_deklarasi ? " · " + t.jml_deklarasi + " ekor" : ""}` +
    `${t.jenis_kelamin ? " · " + t.jenis_kelamin : ""}`;
  const ternakObj = ternakSel && ternakSel !== "lainnya" ? ternakList.find((x) => x.id === ternakSel) : null;
  const jenisHewan = ternakObj ? ternakLabel(ternakObj) : jenisManual;
  const obatPilih = obatList.find((o) => o.id === obatSel) || null;
  const saranDosis = hitungDosis(obatPilih, parseFloat(berat));

  async function runAI() {
    if (aiTeks.trim().length < 5) { setErr("Tulis catatan lapangan dulu untuk dianalisa AI."); return; }
    setErr(null);
    setAiBusy(true);
    try {
      const r = await jpost("/ai/saran", { teks: aiTeks, jenis_hewan: jenisHewan || undefined });
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

  function tambahObat() {
    if (!obatPilih || !obatJml) return;
    const jml = parseFloat(obatJml);
    const pakaiSaran = saranDosis != null && Math.abs(jml - saranDosis) < 0.001;
    setObatDipakai((prev) => [...prev, {
      obat_id: obatPilih.id,
      nama: obatPilih.nama_dagang,
      jumlah: jml,
      satuan: obatPilih.satuan,
      catatan: pakaiSaran ? `${obatPilih.dosis_per_kg} mg/kg × ${berat} kg ÷ ${obatPilih.konsentrasi} mg/${obatPilih.satuan}` : undefined,
    }]);
    setObatSel(""); setObatJml("");
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
      if (ternakObj) {
        body.hewan = {
          ternak_id: ternakObj.id,
          jenis_hewan: ternakLabel(ternakObj),
          jumlah: ternakObj.mode === "populasi" && ternakObj.jml_deklarasi ? ternakObj.jml_deklarasi : 1,
        };
      } else if (jenisManual) {
        body.hewan = { jenis_hewan: jenisManual, jumlah: parseInt(f.jumlah, 10) || 1 };
      }
      if (berat) body.berat_kg = parseFloat(berat);
      if (obatDipakai.length) body.obat = obatDipakai;
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

      <label style={{ fontSize: 13, color: "#666", display: "grid", gap: 4 }}>
        Hewan yang dilayani
        <select style={inp} value={ternakSel} onChange={(e) => setTernakSel(e.target.value)}>
          <option value="">— Pilih ternak terdaftar —</option>
          {ternakList.map((t) => <option key={t.id} value={t.id}>{ternakLabel(t)}</option>)}
          <option value="lainnya">Lainnya (ketik manual)</option>
        </select>
      </label>
      {ternakSel === "lainnya" && (
        <div style={{ display: "flex", gap: 8 }}>
          <input style={inp} placeholder="Jenis hewan (mis. Ayam kampung)" value={jenisManual} onChange={(e) => setJenisManual(e.target.value)} />
          <input style={{ ...inp, width: 90 }} type="number" min="1" placeholder="Jml" value={f.jumlah} onChange={(e) => setF({ ...f, jumlah: e.target.value })} />
        </div>
      )}
      <label style={{ fontSize: 13, color: "#666", display: "grid", gap: 4 }}>
        Berat badan (kg) — untuk hitung dosis
        <input style={inp} type="number" min="0" step="0.1" placeholder="mis. 300" value={berat} onChange={(e) => setBerat(e.target.value)} />
      </label>

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
      <textarea style={{ ...inp, minHeight: 50, fontFamily: "inherit" }} placeholder="Tindakan / pengobatan (teks)" value={f.tindakan} onChange={(e) => setF({ ...f, tindakan: e.target.value })} />

      <div style={{ border: "1px solid #e3e3e3", borderRadius: 10, padding: 12, display: "grid", gap: 8 }}>
        <div style={{ fontSize: 13, color: "#444", fontWeight: 500 }}>💊 Obat dipakai (opsional)</div>
        {obatDipakai.length > 0 && (
          <div style={{ display: "grid", gap: 6 }}>
            {obatDipakai.map((o, i) => (
              <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, fontSize: 14, background: "#f6f6f6", borderRadius: 8, padding: "6px 10px" }}>
                <span>{o.nama} — <strong>{o.jumlah} {o.satuan}</strong>{o.catatan ? <span style={{ color: "#999", fontSize: 12 }}> · {o.catatan}</span> : null}</span>
                <button type="button" onClick={() => setObatDipakai((p) => p.filter((_, j) => j !== i))}
                  style={{ ...btnGhost, padding: "2px 8px", fontSize: 12, color: "#c00", borderColor: "#e0b4b4" }}>Hapus</button>
              </div>
            ))}
          </div>
        )}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <select style={{ ...inp, flex: "1 1 160px" }} value={obatSel} onChange={(e) => setObatSel(e.target.value)}>
            <option value="">— Pilih obat —</option>
            {obatList.map((o) => <option key={o.id} value={o.id}>{o.nama_dagang}</option>)}
          </select>
          <input style={{ ...inp, width: 90 }} type="number" min="0" step="0.1" placeholder="Jumlah" value={obatJml} onChange={(e) => setObatJml(e.target.value)} />
          <span style={{ alignSelf: "center", color: "#666", fontSize: 14, minWidth: 36 }}>{obatPilih ? obatPilih.satuan : ""}</span>
          <button type="button" style={btnGhost} disabled={!obatPilih || !obatJml} onClick={tambahObat}>+ Tambah</button>
        </div>
        {obatPilih && (
          <div style={{ fontSize: 12, color: "#666" }}>
            {saranDosis != null ? (
              <span>
                Saran dosis: <strong>{saranDosis} {obatPilih.satuan}</strong> ({obatPilih.dosis_per_kg} mg/kg × {berat} kg ÷ {obatPilih.konsentrasi} mg/{obatPilih.satuan}) — periksa dulu.{" "}
                <button type="button" onClick={() => setObatJml(String(saranDosis))} style={{ ...btnGhost, padding: "1px 8px", fontSize: 12, borderColor: "#0f6e56", color: "#0f6e56" }}>Pakai</button>
              </span>
            ) : (
              <span style={{ color: "#999" }}>
                {!berat ? "Isi berat badan untuk saran dosis otomatis." : (!obatPilih.dosis_per_kg || !obatPilih.konsentrasi) ? "Obat ini belum punya dosis/konsentrasi acuan — isi jumlah manual." : ""}
              </span>
            )}
            {obatPilih.waktu_henti_daging_hari != null && (
              <div style={{ color: "#a33", marginTop: 2 }}>⚠ Waktu henti: daging {obatPilih.waktu_henti_daging_hari} hari{obatPilih.waktu_henti_susu_jam != null ? `, susu ${obatPilih.waktu_henti_susu_jam} jam` : ""}.</div>
            )}
          </div>
        )}
      </div>

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
        <div style={{ fontSize: 13, color: "#666", marginBottom: 6 }}>Foto kasus (opsional, bisa lebih dari 1)</div>
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
          {p.berat_kg ? <div style={{ fontSize: 13, color: "#666" }}>BB: {p.berat_kg} kg</div> : null}
          {p.obat && p.obat.length > 0 && (
            <div style={{ fontSize: 14 }}>Obat: {p.obat.map((o) => `${o.nama} ${o.jumlah} ${o.satuan}`).join(", ")}</div>
          )}
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

function ObatForm({ initial, onSaved, onCancel }) {
  const isEdit = !!initial;
  const [f, setF] = useState({
    nama_dagang: initial?.nama_dagang || "",
    zat_aktif: initial?.zat_aktif || "",
    konsentrasi: initial?.konsentrasi ?? "",
    satuan: initial?.satuan || "ml",
    dosis_per_kg: initial?.dosis_per_kg ?? "",
    rute: initial?.rute || "",
    waktu_henti_daging_hari: initial?.waktu_henti_daging_hari ?? "",
    waktu_henti_susu_jam: initial?.waktu_henti_susu_jam ?? "",
    aktif: initial?.aktif ?? true,
  });
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);

  const num = (v) => (v === "" || v === null ? null : parseFloat(v));
  const int = (v) => (v === "" || v === null ? null : parseInt(v, 10));

  async function onFotoLabel(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setErr(null);
    setAiBusy(true);
    try {
      const b64 = await new Promise((res, rej) => {
        const r = new FileReader();
        r.onload = () => res(String(r.result).split(",")[1]);
        r.onerror = () => rej(new Error("gagal baca file"));
        r.readAsDataURL(file);
      });
      const d = await jpost("/ai/baca-obat", { image_base64: b64, media_type: file.type || "image/jpeg" });
      const satuanOk = ["ml", "tablet", "bolus", "sachet", "kapsul", "gram"];
      const ruteOk = ["IM", "IV", "SC", "IM/IV", "oral", "topikal"];
      setF((p) => ({
        ...p,
        nama_dagang: d.nama_dagang ?? p.nama_dagang,
        zat_aktif: d.zat_aktif ?? p.zat_aktif,
        konsentrasi: d.konsentrasi ?? p.konsentrasi,
        satuan: d.satuan && satuanOk.includes(String(d.satuan).toLowerCase()) ? String(d.satuan).toLowerCase() : p.satuan,
        dosis_per_kg: d.dosis_per_kg ?? p.dosis_per_kg,
        rute: d.rute && ruteOk.includes(d.rute) ? d.rute : p.rute,
        waktu_henti_daging_hari: d.waktu_henti_daging_hari ?? p.waktu_henti_daging_hari,
        waktu_henti_susu_jam: d.waktu_henti_susu_jam ?? p.waktu_henti_susu_jam,
      }));
    } catch (e2) {
      setErr(String(e2.message || e2));
    } finally {
      setAiBusy(false);
    }
  }

  async function submit() {
    setErr(null);
    setBusy(true);
    try {
      const body = {
        nama_dagang: f.nama_dagang,
        zat_aktif: f.zat_aktif || null,
        konsentrasi: num(f.konsentrasi),
        satuan: f.satuan || "ml",
        dosis_per_kg: num(f.dosis_per_kg),
        rute: f.rute || null,
        waktu_henti_daging_hari: int(f.waktu_henti_daging_hari),
        waktu_henti_susu_jam: int(f.waktu_henti_susu_jam),
        aktif: f.aktif,
      };
      const o = isEdit ? await jpatch(`/obat/${initial.id}`, body) : await jpost("/obat", body);
      onSaved(o);
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ ...card, display: "grid", gap: 10, background: "#fafafa" }}>
      <strong>{isEdit ? "Edit Obat" : "Tambah Obat"}</strong>
      <div style={{ border: "1px dashed #d6a700", borderRadius: 10, padding: 10, background: "#fffdf5", display: "grid", gap: 6 }}>
        <label style={{ ...btnGhost, borderColor: "#d6a700", color: "#9a7b00", display: "block", textAlign: "center", cursor: aiBusy ? "default" : "pointer" }}>
          {aiBusy ? "Membaca label…" : "📷 Foto label obat — AI isi otomatis"}
          <input type="file" accept="image/*" style={{ display: "none" }} onChange={onFotoLabel} disabled={aiBusy} />
        </label>
        <div style={{ fontSize: 11, color: "#999" }}>AI membaca yang tercetak di label. Periksa &amp; koreksi angka (konsentrasi/dosis) sebelum simpan.</div>
      </div>
      <input style={inp} placeholder="Nama dagang *" value={f.nama_dagang} onChange={(e) => setF({ ...f, nama_dagang: e.target.value })} />
      <input style={inp} placeholder="Zat aktif (mis. Oksitetrasiklin)" value={f.zat_aktif} onChange={(e) => setF({ ...f, zat_aktif: e.target.value })} />
      <div style={{ display: "flex", gap: 8 }}>
        <input style={inp} type="number" step="0.01" placeholder="Konsentrasi (mg per satuan)" value={f.konsentrasi} onChange={(e) => setF({ ...f, konsentrasi: e.target.value })} />
        <select style={{ ...inp, width: 130 }} value={f.satuan} onChange={(e) => setF({ ...f, satuan: e.target.value })}>
          <option value="ml">ml</option><option value="tablet">tablet</option><option value="bolus">bolus</option>
          <option value="sachet">sachet</option><option value="kapsul">kapsul</option><option value="gram">gram</option>
        </select>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <input style={inp} type="number" step="0.01" placeholder="Dosis (mg/kg)" value={f.dosis_per_kg} onChange={(e) => setF({ ...f, dosis_per_kg: e.target.value })} />
        <select style={{ ...inp, width: 130 }} value={f.rute} onChange={(e) => setF({ ...f, rute: e.target.value })}>
          <option value="">— Rute —</option>
          <option>IM</option><option>IV</option><option>SC</option><option>IM/IV</option><option>oral</option><option>topikal</option>
        </select>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <input style={inp} type="number" placeholder="Waktu henti daging (hari)" value={f.waktu_henti_daging_hari} onChange={(e) => setF({ ...f, waktu_henti_daging_hari: e.target.value })} />
        <input style={inp} type="number" placeholder="Waktu henti susu (jam)" value={f.waktu_henti_susu_jam} onChange={(e) => setF({ ...f, waktu_henti_susu_jam: e.target.value })} />
      </div>
      <label style={{ fontSize: 14, display: "flex", gap: 8, alignItems: "center" }}>
        <input type="checkbox" checked={f.aktif} onChange={(e) => setF({ ...f, aktif: e.target.checked })} /> Aktif (tampil di pilihan obat saat pelayanan)
      </label>
      <div style={{ fontSize: 12, color: "#999" }}>Konsentrasi = mg per 1 satuan (mis. 200 = 200 mg/ml). Konsentrasi + dosis/kg diperlukan agar saran dosis otomatis bisa dihitung.</div>
      {err && <div style={{ color: "#c00", fontSize: 14 }}>{err}</div>}
      <div style={{ display: "flex", gap: 8 }}>
        <button style={btn} disabled={busy || !f.nama_dagang} onClick={submit}>{busy ? "Menyimpan…" : (isEdit ? "Simpan perubahan" : "Simpan")}</button>
        <button style={btnGhost} onClick={onCancel}>Batal</button>
      </div>
    </div>
  );
}

function ObatPage({ isAdmin }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    jget("/obat?semua=true").then(setItems).catch(() => setItems([])).finally(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  async function hapus(o) {
    if (!window.confirm(`Hapus obat "${o.nama_dagang}"? Permanen.`)) return;
    try {
      await jdel(`/obat/${o.id}`);
      load();
    } catch (e) {
      window.alert(e.message || e);
    }
  }

  if (editing) return <ObatForm initial={editing} onCancel={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />;

  return (
    <div style={{ display: "grid", gap: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <strong>Daftar Obat (formularium)</strong>
        <button style={btn} onClick={() => setShowForm((s) => !s)}>{showForm ? "Tutup" : "+ Tambah obat"}</button>
      </div>
      {showForm && <ObatForm onCancel={() => setShowForm(false)} onSaved={() => { setShowForm(false); load(); }} />}
      {loading ? <div style={{ color: "#888" }}>memuat…</div> : !items.length ? <div style={{ color: "#888" }}>Belum ada obat.</div> : (
        <div style={{ display: "grid", gap: 8 }}>
          {items.map((o) => (
            <div key={o.id} style={{ ...card, display: "flex", justifyContent: "space-between", gap: 8, alignItems: "flex-start", opacity: o.aktif === false ? 0.5 : 1 }}>
              <div>
                <div style={{ fontWeight: 500 }}>{o.nama_dagang}{o.aktif === false ? " (nonaktif)" : ""}</div>
                <div style={{ fontSize: 13, color: "#666" }}>
                  {o.zat_aktif || "—"}
                  {o.konsentrasi != null ? ` · ${o.konsentrasi} mg/${o.satuan}` : ""}
                  {o.dosis_per_kg != null ? ` · ${o.dosis_per_kg} mg/kg` : ""}
                  {o.rute ? ` · ${o.rute}` : ""}
                </div>
                {(o.waktu_henti_daging_hari != null || o.waktu_henti_susu_jam != null) && (
                  <div style={{ fontSize: 12, color: "#a33" }}>
                    Waktu henti: {o.waktu_henti_daging_hari != null ? `daging ${o.waktu_henti_daging_hari} hari` : ""}
                    {o.waktu_henti_daging_hari != null && o.waktu_henti_susu_jam != null ? ", " : ""}
                    {o.waktu_henti_susu_jam != null ? `susu ${o.waktu_henti_susu_jam} jam` : ""}
                  </div>
                )}
              </div>
              <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                <button style={btnGhost} onClick={() => setEditing(o)}>Edit</button>
                {isAdmin && <button style={{ ...btnGhost, color: "#c00", borderColor: "#e0b4b4" }} onClick={() => hapus(o)}>Hapus</button>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ternakDraftPayload(items) {
  return items.filter((t) => t.spesies).map((t) => {
    const o = { spesies: t.spesies, mode: t.mode };
    if (t.ras_id) o.ras_id = t.ras_id;
    if (t.mode === "individu") {
      if (t.eartag) o.eartag = t.eartag;
      if (t.jenis_kelamin) o.jenis_kelamin = t.jenis_kelamin;
    } else if (t.jml_deklarasi) {
      o.jml_deklarasi = parseInt(t.jml_deklarasi, 10);
    }
    return o;
  });
}

function TernakDraftRow({ t, spesiesList, onUpd, onDel }) {
  const [rasList, setRasList] = useState([]);
  useEffect(() => {
    if (t.spesies) jget(`/ras?spesies=${encodeURIComponent(t.spesies)}`).then(setRasList).catch(() => setRasList([]));
    else setRasList([]);
  }, [t.spesies]);
  return (
    <div style={{ ...card, display: "grid", gap: 8, background: "#fafafa" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <strong style={{ fontSize: 13 }}>Ternak</strong>
        <button type="button" onClick={onDel} style={{ ...btnGhost, padding: "2px 8px", fontSize: 12, color: "#c00", borderColor: "#e0b4b4" }}>Hapus</button>
      </div>
      <select style={inp} value={t.spesies} onChange={(e) => onUpd({ spesies: e.target.value, ras_id: "" })}>
        <option value="">— Spesies * —</option>
        {spesiesList.map((s) => <option key={s} value={s}>{s}</option>)}
      </select>
      <select style={inp} value={t.ras_id} disabled={!t.spesies} onChange={(e) => onUpd({ ras_id: e.target.value })}>
        <option value="">— Ras —</option>
        {rasList.map((r) => <option key={r.id} value={r.id}>{r.nama}</option>)}
      </select>
      <select style={inp} value={t.mode} onChange={(e) => onUpd({ mode: e.target.value })}>
        <option value="individu">Individu (per ekor)</option>
        <option value="populasi">Populasi (kelompok)</option>
      </select>
      {t.mode === "individu" ? (
        <div style={{ display: "flex", gap: 8 }}>
          <input style={inp} placeholder="Eartag / nomor" value={t.eartag} onChange={(e) => onUpd({ eartag: e.target.value })} />
          <select style={{ ...inp, width: 130 }} value={t.jenis_kelamin} onChange={(e) => onUpd({ jenis_kelamin: e.target.value })}>
            <option value="">— Kelamin —</option><option value="betina">Betina</option><option value="jantan">Jantan</option>
          </select>
        </div>
      ) : (
        <input style={inp} type="number" min="1" placeholder="Jumlah ekor" value={t.jml_deklarasi} onChange={(e) => onUpd({ jml_deklarasi: e.target.value })} />
      )}
    </div>
  );
}

function TernakDraftEditor({ items, onChange }) {
  const [spesiesList, setSpesiesList] = useState([]);
  useEffect(() => { jget("/ras/spesies").then(setSpesiesList).catch(() => {}); }, []);
  const add = () => onChange([...items, { spesies: "", ras_id: "", mode: "individu", eartag: "", jenis_kelamin: "", jml_deklarasi: "" }]);
  const upd = (i, patch) => onChange(items.map((t, j) => (j === i ? { ...t, ...patch } : t)));
  const del = (i) => onChange(items.filter((_, j) => j !== i));
  return (
    <div style={{ display: "grid", gap: 10 }}>
      {items.map((t, i) => <TernakDraftRow key={i} t={t} spesiesList={spesiesList} onUpd={(p) => upd(i, p)} onDel={() => del(i)} />)}
      <button type="button" style={btnGhost} onClick={add}>+ Tambah ternak</button>
    </div>
  );
}

function PublicDaftar() {
  const [f, setF] = useState({ nama: "", kontak: "", nik: "", alamat_detail: "", catatan: "" });
  const [wil, setWil] = useState({ kapanewon_id: null, kalurahan_id: null, padukuhan_id: null });
  const [koord, setKoord] = useState(null);
  const [gps, setGps] = useState("");
  const [ternak, setTernak] = useState([]);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  // Konteks dari QR, mis. #/daftar?kalurahan=<id>
  useEffect(() => {
    const h = window.location.hash || "";
    const q = h.includes("?") ? new URLSearchParams(h.split("?")[1]) : null;
    if (q) {
      const kap = q.get("kapanewon"), kal = q.get("kalurahan");
      if (kap || kal) setWil((w) => ({ ...w, kapanewon_id: kap || w.kapanewon_id, kalurahan_id: kal || w.kalurahan_id }));
    }
  }, []);

  function ambilGPS() {
    if (!navigator.geolocation) { setGps("perangkat tak mendukung lokasi"); return; }
    setGps("mengambil…");
    navigator.geolocation.getCurrentPosition(
      (p) => { setKoord({ lat: p.coords.latitude, lng: p.coords.longitude }); setGps("lokasi terekam ✓"); },
      () => setGps("gagal ambil lokasi"),
      { enableHighAccuracy: true, timeout: 10000 }
    );
  }

  async function submit() {
    setErr(null);
    setBusy(true);
    try {
      const body = { ...f, ...wil, sumber: "qr", ternak: ternakDraftPayload(ternak) };
      if (!body.nik) delete body.nik;
      if (koord) body.koordinat = koord;
      await jpost("/pendaftaran", body);
      setDone(true);
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  const wrap = { maxWidth: 520, margin: "3vh auto", padding: 16 };

  if (done) {
    return (
      <div style={wrap}>
        <div style={{ ...card, textAlign: "center", display: "grid", gap: 10 }}>
          <div style={{ fontSize: 40 }}>✅</div>
          <h2 style={{ margin: 0, fontWeight: 600 }}>Pendaftaran terkirim</h2>
          <p style={{ color: "#666", margin: 0 }}>Terima kasih. Tunjukkan layar ini ke petugas untuk verifikasi, atau tunggu petugas menghubungi.</p>
          <button style={btnGhost} onClick={() => { setDone(false); setF({ nama: "", kontak: "", nik: "", alamat_detail: "", catatan: "" }); setWil({ kapanewon_id: null, kalurahan_id: null, padukuhan_id: null }); setTernak([]); setKoord(null); setGps(""); }}>Daftar lagi</button>
        </div>
      </div>
    );
  }

  return (
    <div style={wrap}>
      <h1 style={{ fontWeight: 600, fontSize: 22, marginBottom: 2 }}>Pendaftaran Peternak</h1>
      <p style={{ color: "#666", marginTop: 0, fontSize: 14 }}>Puskeswan Godean — isi data diri & ternak Anda.</p>
      <div style={{ ...card, display: "grid", gap: 10 }}>
        <input style={inp} placeholder="Nama lengkap *" value={f.nama} onChange={(e) => setF({ ...f, nama: e.target.value })} />
        <input style={inp} placeholder="No. HP / WhatsApp *" value={f.kontak} onChange={(e) => setF({ ...f, kontak: e.target.value })} />
        <input style={inp} placeholder="NIK (opsional)" value={f.nik} onChange={(e) => setF({ ...f, nik: e.target.value })} />
        <div style={{ fontSize: 13, color: "#666" }}>Wilayah</div>
        <WilayahCascade value={wil} onChange={setWil} />
        <input style={inp} placeholder="Alamat detail (RT/RW, patokan)" value={f.alamat_detail} onChange={(e) => setF({ ...f, alamat_detail: e.target.value })} />
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button type="button" style={btnGhost} onClick={ambilGPS}>📍 Ambil lokasi GPS</button>
          <span style={{ fontSize: 13, color: "#666" }}>{gps}</span>
        </div>

        <div style={{ fontSize: 13, color: "#666", marginTop: 4 }}>Ternak yang dimiliki</div>
        <TernakDraftEditor items={ternak} onChange={setTernak} />

        <input style={inp} placeholder="Catatan / keluhan (opsional)" value={f.catatan} onChange={(e) => setF({ ...f, catatan: e.target.value })} />
        {err && <div style={{ color: "#c00", fontSize: 14 }}>{err}</div>}
        <button style={btn} disabled={busy || !f.nama || !f.kontak} onClick={submit}>{busy ? "Mengirim…" : "Kirim pendaftaran"}</button>
        <div style={{ fontSize: 11, color: "#999" }}>Data Anda akan diverifikasi petugas sebelum tercatat resmi.</div>
      </div>
    </div>
  );
}

function PendaftaranConfirm({ item, onBack, onDone }) {
  const [f, setF] = useState({ nama: item.nama || "", kontak: item.kontak || "", nik: item.nik || "", alamat_detail: item.alamat_detail || "" });
  const [wil, setWil] = useState({ kapanewon_id: item.kapanewon_id || null, kalurahan_id: item.kalurahan_id || null, padukuhan_id: item.padukuhan_id || null });
  const [ternak, setTernak] = useState((item.ternak || []).map((t) => ({
    spesies: t.spesies || "", ras_id: t.ras_id || "", mode: t.mode || "individu",
    eartag: t.eartag || "", jenis_kelamin: t.jenis_kelamin || "", jml_deklarasi: t.jml_deklarasi ?? "",
  })));
  const koord = item.koordinat ? { lat: item.koordinat.coordinates[1], lng: item.koordinat.coordinates[0] } : null;
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  async function konfirmasi() {
    setErr(null);
    setBusy(true);
    try {
      const body = { ...f, ...wil, ternak: ternakDraftPayload(ternak) };
      if (!body.nik) delete body.nik;
      if (koord) body.koordinat = koord;
      await jpost(`/pendaftaran/${item.id}/konfirmasi`, body);
      onDone();
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }
  async function tolak() {
    if (!window.confirm("Tolak pendaftaran ini? Data tidak akan dibuat.")) return;
    try {
      await jpost(`/pendaftaran/${item.id}/tolak`, {});
      onDone();
    } catch (e) {
      window.alert(e.message || e);
    }
  }

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <button style={btnGhost} onClick={onBack}>← Kembali ke antrian</button>
      <div style={{ ...card, display: "grid", gap: 10, background: "#fafafa" }}>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <strong>Verifikasi Pendaftaran</strong>
          <span style={{ fontSize: 12, color: "#9a7b00" }}>sumber: {item.sumber || "—"}</span>
        </div>
        <input style={inp} placeholder="Nama *" value={f.nama} onChange={(e) => setF({ ...f, nama: e.target.value })} />
        <input style={inp} placeholder="Kontak *" value={f.kontak} onChange={(e) => setF({ ...f, kontak: e.target.value })} />
        <input style={inp} placeholder="NIK (opsional)" value={f.nik} onChange={(e) => setF({ ...f, nik: e.target.value })} />
        <WilayahCascade value={wil} onChange={setWil} />
        <input style={inp} placeholder="Alamat detail" value={f.alamat_detail} onChange={(e) => setF({ ...f, alamat_detail: e.target.value })} />
        {item.catatan && <div style={{ fontSize: 13, color: "#666" }}>Catatan pemohon: {item.catatan}</div>}
        {koord && <div style={{ fontSize: 13, color: "#0f6e56" }}>📍 Lokasi GPS terlampir</div>}
        <div style={{ fontSize: 13, color: "#666", marginTop: 4 }}>Ternak</div>
        <TernakDraftEditor items={ternak} onChange={setTernak} />
        {err && <div style={{ color: "#c00", fontSize: 14 }}>{err}</div>}
        <div style={{ display: "flex", gap: 8 }}>
          <button style={btn} disabled={busy || !f.nama || !f.kontak} onClick={konfirmasi}>{busy ? "Memproses…" : "Konfirmasi & buat data"}</button>
          <button style={{ ...btnGhost, color: "#c00", borderColor: "#e0b4b4" }} onClick={tolak}>Tolak</button>
        </div>
      </div>
    </div>
  );
}

function PendaftaranPage({ onConfirmed }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [sel, setSel] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    jget("/pendaftaran?status=baru").then(setItems).catch(() => setItems([])).finally(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  if (sel) return <PendaftaranConfirm item={sel} onBack={() => setSel(null)} onDone={() => { setSel(null); load(); onConfirmed && onConfirmed(); }} />;

  return (
    <div style={{ display: "grid", gap: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <strong>Antrian Pendaftaran</strong>
        <button style={btnGhost} onClick={load}>Muat ulang</button>
      </div>
      {loading ? <div style={{ color: "#888" }}>memuat…</div> : !items.length ? <div style={{ color: "#888" }}>Tidak ada pendaftaran menunggu.</div> : (
        <div style={{ display: "grid", gap: 8 }}>
          {items.map((d) => (
            <div key={d.id} style={{ ...card, cursor: "pointer" }} onClick={() => setSel(d)}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <strong>{d.nama}</strong>
                <span style={{ fontSize: 12, color: "#9a7b00" }}>{d.sumber || "—"}</span>
              </div>
              <div style={{ fontSize: 13, color: "#666" }}>{d.kontak}{d.ternak && d.ternak.length ? ` · ${d.ternak.length} ternak` : " · belum ada ternak"}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const BULAN_NAMA = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"];

function StatBox({ label, val }) {
  return (
    <div style={{ ...card, textAlign: "center" }}>
      <div style={{ fontSize: 22, fontWeight: 600, color: "#0f6e56" }}>{val}</div>
      <div style={{ fontSize: 12, color: "#666" }}>{label}</div>
    </div>
  );
}

function SeksiTabel({ judul, kolom, baris }) {
  if (!baris.length) return null;
  return (
    <div style={card}>
      <strong style={{ fontSize: 14 }}>{judul}</strong>
      <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 6, fontSize: 14 }}>
        <thead>
          <tr>{kolom.map((k, i) => (
            <th key={i} style={{ textAlign: i === kolom.length - 1 ? "right" : "left", color: "#888", fontWeight: 500, padding: "4px 0", borderBottom: "1px solid #eee" }}>{k}</th>
          ))}</tr>
        </thead>
        <tbody>
          {baris.map((b, i) => (
            <tr key={i}>{b.map((c, j) => (
              <td key={j} style={{ textAlign: j === b.length - 1 ? "right" : "left", padding: "4px 0", borderBottom: "1px solid #f3f3f3" }}>{c}</td>
            ))}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LaporanPage() {
  const now = new Date();
  const [periode, setPeriode] = useState(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`);
  const [wil, setWil] = useState({ kapanewon_id: null, kalurahan_id: null, padukuhan_id: null });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  async function tampilkan() {
    setErr(null);
    setLoading(true);
    setData(null);
    try {
      const [y, m] = periode.split("-");
      let url = `/laporan/bulanan?tahun=${parseInt(y, 10)}&bulan=${parseInt(m, 10)}`;
      if (wil.kalurahan_id) url += `&kalurahan_id=${wil.kalurahan_id}`;
      setData(await jget(url));
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setLoading(false);
    }
  }

  function unduhCSV() {
    if (!data) return;
    const rows = [];
    const push = (...cols) => rows.push(cols.map((c) => `"${String(c ?? "").replace(/"/g, '""')}"`).join(","));
    push("REKAP BULANAN", `${BULAN_NAMA[data.periode.bulan]} ${data.periode.tahun}`);
    push("");
    push("Ringkasan");
    push("Total pelayanan", data.pelayanan.total);
    push("Peternak baru", data.peternak_baru);
    push("Pendaftaran baru", data.pendaftaran.baru);
    push("Pendaftaran dikonfirmasi", data.pendaftaran.dikonfirmasi);
    push("");
    push("Mutasi ternak");
    Object.entries(data.ternak_mutasi).forEach(([k, v]) => push(k, v));
    push("");
    push("Per penyakit (iSIKHNAS)"); push("Kode", "Nama", "Jumlah");
    data.pelayanan.per_penyakit.forEach((x) => push(x.kode, x.nama, x.jumlah));
    push("");
    push("Per wilayah"); push("Kalurahan", "Jumlah");
    data.pelayanan.per_wilayah.forEach((x) => push(x.nama, x.jumlah));
    push("");
    push("Per petugas"); push("Petugas", "Jumlah");
    data.pelayanan.per_petugas.forEach((x) => push(x.nama, x.jumlah));
    push("");
    push("Pemakaian obat"); push("Obat", "Jumlah", "Satuan");
    data.obat.forEach((x) => push(x.nama, x.jumlah, x.satuan));
    const blob = new Blob(["\ufeff" + rows.join("\n")], { type: "text/csv;charset=utf-8;" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `rekap-${data.periode.tahun}-${String(data.periode.bulan).padStart(2, "0")}.csv`;
    a.click();
  }

  const ringkas = (obj) => Object.entries(obj || {}).map(([k, v]) => `${k}: ${v}`).join(" · ") || "—";

  return (
    <div style={{ display: "grid", gap: 12 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <input style={{ ...inp, width: 170 }} type="month" value={periode} onChange={(e) => setPeriode(e.target.value)} />
        <button style={btn} disabled={loading} onClick={tampilkan}>{loading ? "Memuat…" : "Tampilkan"}</button>
        {data && <button style={btnGhost} onClick={unduhCSV}>⬇ Unduh CSV</button>}
      </div>
      <div>
        <div style={{ fontSize: 13, color: "#666", marginBottom: 4 }}>Filter wilayah (opsional)</div>
        <WilayahCascade value={wil} onChange={setWil} />
      </div>
      {err && <div style={{ color: "#c00" }}>{err}</div>}
      {data && (
        <div style={{ display: "grid", gap: 12 }}>
          <div style={{ color: "#666", fontSize: 14 }}>Periode: <strong>{BULAN_NAMA[data.periode.bulan]} {data.periode.tahun}</strong></div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: 8 }}>
            <StatBox label="Total pelayanan" val={data.pelayanan.total} />
            <StatBox label="Peternak baru" val={data.peternak_baru} />
            <StatBox label="Pendaftaran baru" val={data.pendaftaran.baru} />
            <StatBox label="Kematian ternak" val={data.ternak_mutasi.mati || 0} />
          </div>
          <div style={{ ...card, fontSize: 13, color: "#555" }}>
            <div>Metode: {ringkas(data.pelayanan.per_metode)}</div>
            <div>Prognosa: {ringkas(data.pelayanan.per_prognosa)}</div>
            <div>Mutasi ternak: {ringkas(data.ternak_mutasi)}</div>
          </div>
          <SeksiTabel judul="Per penyakit (iSIKHNAS)" kolom={["Kode", "Nama", "Jumlah"]}
            baris={data.pelayanan.per_penyakit.map((x) => [x.kode, x.nama, x.jumlah])} />
          <SeksiTabel judul="Per wilayah" kolom={["Kalurahan", "Jumlah"]}
            baris={data.pelayanan.per_wilayah.map((x) => [x.nama, x.jumlah])} />
          <SeksiTabel judul="Per petugas" kolom={["Petugas", "Jumlah"]}
            baris={data.pelayanan.per_petugas.map((x) => [x.nama, x.jumlah])} />
          <SeksiTabel judul="Pemakaian obat" kolom={["Obat", "Jumlah", "Satuan"]}
            baris={data.obat.map((x) => [x.nama, x.jumlah, x.satuan])} />
          {data.pelayanan.total === 0 && <div style={{ color: "#888" }}>Tidak ada pelayanan pada periode ini.</div>}
        </div>
      )}
    </div>
  );
}

function Shell({ user, onLogout }) {
  const [role, setRole] = useState(user.roles.length === 1 ? user.roles[0] : null);
  const [tab, setTab] = useState("peternak");
  const [pendaftaranBaru, setPendaftaranBaru] = useState(0);
  const refreshPendaftaran = useCallback(() => {
    jget("/pendaftaran/count").then((d) => setPendaftaranBaru(d.baru || 0)).catch(() => {});
  }, []);
  useEffect(() => { if (role === "admin" || role === "petugas") refreshPendaftaran(); }, [role, refreshPendaftaran]);
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
        <>
          <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap" }}>
            <button style={tab === "peternak" ? btn : btnGhost} onClick={() => setTab("peternak")}>Peternak</button>
            <button style={tab === "obat" ? btn : btnGhost} onClick={() => setTab("obat")}>Obat</button>
            <button style={tab === "pendaftaran" ? btn : btnGhost} onClick={() => { setTab("pendaftaran"); refreshPendaftaran(); }}>
              Pendaftaran{pendaftaranBaru ? ` (${pendaftaranBaru})` : ""}
            </button>
            <button style={tab === "laporan" ? btn : btnGhost} onClick={() => setTab("laporan")}>Laporan</button>
          </div>
          {tab === "peternak" && <PeternakPage isAdmin={user.roles.includes("admin")} />}
          {tab === "obat" && <ObatPage isAdmin={user.roles.includes("admin")} />}
          {tab === "pendaftaran" && <PendaftaranPage onConfirmed={refreshPendaftaran} />}
          {tab === "laporan" && <LaporanPage />}
        </>
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

  const isDaftar = typeof window !== "undefined" && (window.location.hash || "").startsWith("#/daftar");
  if (isDaftar) {
    return (
      <div style={{ fontFamily: "system-ui, sans-serif" }}>
        <PublicDaftar />
      </div>
    );
  }

  return (
    <div style={{ fontFamily: "system-ui, sans-serif" }}>
      {user ? <Shell user={user} onLogout={logout} /> : <Login onLogin={setUser} />}
    </div>
  );
}
