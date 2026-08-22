import csv
import io
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st
import pandas as pd
import requests

# ============================================================
# 1. Konfigurasi Halaman
# ============================================================
st.set_page_config(page_title="Kalender Ekonomi", layout="wide", page_icon="calendar")
st.title("Kalender Ekonomi")
st.caption(
    "Jadwal rilis data ekonomi penting (CPI, NFP, suku bunga, GDP, PMI, dll) untuk minggu lalu/ini/depan "
    "— pilih periode di sidebar — beserta jadwal review indeks MSCI. Kalender ekonomi bersumber dari "
    "feed publik ForexFactory.com; jadwal review indeks bersumber dari rilis resmi msci.com."
)

# ============================================================
# 2. Styling — konsisten dengan halaman lain
# ============================================================
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, .stApp, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }
    #MainMenu, footer, [data-testid="stDecoration"] { visibility: hidden; height: 0; }
    h1 { font-weight: 700; letter-spacing: -0.02em; }
    h2, h3 { font-weight: 600; letter-spacing: -0.01em; }
    .stButton > button, .stDownloadButton > button {
        border-radius: 8px;
        border: 1px solid rgba(128,128,128,0.25);
        font-weight: 500;
        transition: all 0.15s ease;
    }
    .stButton > button:hover, .stDownloadButton > button:hover {
        border-color: #2962ff;
        color: #2962ff;
    }
    [data-testid="stExpander"] { border: 1px solid rgba(128,128,128,0.15); border-radius: 10px; }

    .sorotan-card {
        background-color: rgba(151, 166, 195, 0.10);
        border: 1px solid rgba(151, 166, 195, 0.30);
        border-radius: 12px;
        padding: 16px 18px;
        height: 100%;
    }
    .sorotan-card .label { font-size: 12px; color: #8a8f99; margin-bottom: 4px; }
    .sorotan-card .judul { font-size: 16px; font-weight: 700; margin-bottom: 2px; }
    .sorotan-card .sub { font-size: 13px; color: #a8adb8; }

    .badge-impact {
        display: inline-block;
        letter-spacing: 1px;
        font-size: 13px;
        margin-left: 4px;
    }
    .bintang-isi { color: #f4b400; }
    .bintang-kosong { color: #3a3f4b; }

    .event-row {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 8px 4px;
        border-bottom: 1px solid rgba(151, 166, 195, 0.14);
        font-size: 13.5px;
    }
    .event-row .waktu { width: 64px; color: #8a8f99; flex-shrink: 0; }
    .event-row .mata-uang { width: 46px; flex-shrink: 0; font-weight: 600; }
    .event-row .judul-event { flex: 1; }
    .event-row .angka { width: 70px; text-align: right; color: #a8adb8; flex-shrink: 0; font-size: 12.5px; }
    </style>
    """,
    unsafe_allow_html=True,
)

WIB = ZoneInfo("Asia/Jakarta")

PETA_URL_PERIODE = {
    "Minggu Lalu": "https://nfs.faireconomy.media/ff_calendar_lastweek.json",
    "Minggu Ini": "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
    "Minggu Depan": "https://nfs.faireconomy.media/ff_calendar_nextweek.json",
}
URL_MSCI_CSV = "https://app2.msci.com/eqb/pressreleases/archive/ir_dates.csv"

BENDERA_MATA_UANG = {
    "USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧", "JPY": "🇯🇵", "CNY": "🇨🇳",
    "AUD": "🇦🇺", "NZD": "🇳🇿", "CAD": "🇨🇦", "CHF": "🇨🇭", "IDR": "🇮🇩",
}

KATA_KUNCI_PENTING = [
    "cpi", "nfp", "non-farm", "non farm", "payroll", "gdp", "interest rate",
    "fomc", "ppi", "retail sales", "unemployment rate", "pmi", "rate decision",
    "employment change", "trade balance",
]

JUMLAH_BINTANG = {"Low": 1, "Medium": 2, "High": 3}


def render_bintang(dampak: str) -> str:
    """Render dampak sebagai bintang ala ForexFactory: Low=1, Medium=2, High=3 dari 3 bintang."""
    n = JUMLAH_BINTANG.get(dampak, 1)
    isi = '<span class="bintang-isi">' + "★" * n + "</span>"
    kosong = '<span class="bintang-kosong">' + "★" * (3 - n) + "</span>"
    return f'<span class="badge-impact">{isi}{kosong}</span>'


# ============================================================
# 3. Ambil data kalender ekonomi dari ForexFactory (feed publik)
#    Catatan: ForexFactory membatasi permintaan file kalender mingguan
#    (maks. sekitar 2x per 5 menit), jadi hasil di-cache 30 menit.
#    Feed publik mereka hanya menyediakan 3 periode: minggu lalu, minggu
#    ini, dan minggu depan — belum ada cakupan bulanan dari sumber ini.
# ============================================================
@st.cache_data(ttl=1800, show_spinner=False)
def ambil_kalender_ff(url: str):
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return pd.DataFrame(), None
        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"], utc=True).dt.tz_convert(WIB)
        df = df.sort_values("date").reset_index(drop=True)
        df = df.rename(columns={
            "title": "Event", "country": "MataUang", "date": "Waktu",
            "impact": "Dampak", "forecast": "Forecast", "previous": "Previous",
        })
        return df, None
    except Exception as e:
        return pd.DataFrame(), str(e)


# ============================================================
# 4. Ambil jadwal review indeks MSCI dari rilis resmi msci.com
#    (berisi 8 jadwal review reguler berikutnya, diterbitkan tiap kuartal).
# ============================================================
@st.cache_data(ttl=21600, show_spinner=False)
def ambil_jadwal_msci():
    try:
        resp = requests.get(URL_MSCI_CSV, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        teks = resp.text

        baris_data = []
        mulai = False
        for baris in teks.splitlines():
            baris = baris.strip()
            if baris.startswith("#BOD"):
                mulai = True
                continue
            if baris.startswith("#EOD"):
                break
            if mulai and baris:
                pembaca = csv.reader(io.StringIO(baris))
                row = next(pembaca, None)
                if not row or not row[0]:
                    continue
                bagian = row[0].split("|")
                if len(bagian) >= 4 and bagian[0].strip() != "Quarter":
                    kuartal = bagian[0].strip()
                    event_nama = bagian[1].strip().strip('"')
                    tgl_umum = bagian[2].strip()
                    tgl_efektif = bagian[3].strip()
                    baris_data.append({
                        "Kuartal": kuartal,
                        "Event": event_nama,
                        "Tanggal Pengumuman": tgl_umum,
                        "Tanggal Efektif": tgl_efektif,
                    })

        if not baris_data:
            return pd.DataFrame(), "Format data MSCI berubah, tidak bisa diproses."

        df = pd.DataFrame(baris_data)
        df["_tgl_efektif_dt"] = pd.to_datetime(df["Tanggal Efektif"], format="%m-%d-%Y", errors="coerce")
        df["_tgl_umum_dt"] = pd.to_datetime(df["Tanggal Pengumuman"], format="%m-%d-%Y", errors="coerce")
        return df, None
    except Exception as e:
        return pd.DataFrame(), str(e)


st.sidebar.header("Filter Kalender Ekonomi")

periode_dipilih = st.sidebar.selectbox(
    "Periode",
    options=list(PETA_URL_PERIODE.keys()),
    index=1,
)
st.sidebar.caption(
    "Feed publik ForexFactory hanya menyediakan 3 periode ini (minggu lalu/ini/depan) — "
    "belum ada cakupan bulanan langsung dari sumber ini."
)

col_judul, col_refresh = st.columns([5, 1])
with col_refresh:
    if st.button("Refresh Data", use_container_width=True):
        ambil_kalender_ff.clear()
        ambil_jadwal_msci.clear()
        st.rerun()

df_ff, error_ff = ambil_kalender_ff(PETA_URL_PERIODE[periode_dipilih])
df_msci, error_msci = ambil_jadwal_msci()

if error_ff:
    st.error(f"Gagal mengambil kalender ekonomi dari ForexFactory: {error_ff}")
if error_msci:
    st.warning(f"Gagal mengambil jadwal review MSCI: {error_msci}")

st.markdown("---")

# ============================================================
# 5. Sorotan — CPI AS berikutnya, review MSCI berikutnya, rilis dampak tinggi berikutnya
# ============================================================
sekarang = datetime.now(WIB)

sorot1, sorot2, sorot3 = st.columns(3)

with sorot1:
    cpi_usd_mendatang = pd.DataFrame()
    if not df_ff.empty:
        cpi_usd_mendatang = df_ff[
            (df_ff["MataUang"] == "USD")
            & (df_ff["Event"].str.contains("CPI", case=False, na=False))
            & (df_ff["Waktu"] >= sekarang)
        ]
    if not cpi_usd_mendatang.empty:
        ev = cpi_usd_mendatang.iloc[0]
        st.markdown(
            f"""
            <div class="sorotan-card">
                <div class="label">🇺🇸 CPI AS Berikutnya</div>
                <div class="judul">{ev['Event']}</div>
                <div class="sub">{ev['Waktu'].strftime('%A, %d %b %Y — %H:%M WIB')}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div class="sorotan-card">
                <div class="label">🇺🇸 CPI AS Berikutnya</div>
                <div class="judul">Tidak ada dalam periode "{periode_dipilih}"</div>
                <div class="sub">Coba pilih periode lain di sidebar</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

with sorot2:
    if not df_msci.empty:
        msci_mendatang = df_msci[df_msci["_tgl_efektif_dt"] >= sekarang.replace(tzinfo=None)]
        if not msci_mendatang.empty:
            ev = msci_mendatang.iloc[0]
            st.markdown(
                f"""
                <div class="sorotan-card">
                    <div class="label">📊 Review Indeks MSCI Berikutnya</div>
                    <div class="judul">{ev['Kuartal']} {ev['Event']}</div>
                    <div class="sub">Efektif {ev['Tanggal Efektif']} · Diumumkan {ev['Tanggal Pengumuman']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                """
                <div class="sorotan-card">
                    <div class="label">📊 Review Indeks MSCI Berikutnya</div>
                    <div class="judul">Data tidak tersedia</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            """
            <div class="sorotan-card">
                <div class="label">📊 Review Indeks MSCI Berikutnya</div>
                <div class="judul">Data tidak tersedia</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

with sorot3:
    dampak_tinggi_mendatang = pd.DataFrame()
    if not df_ff.empty:
        dampak_tinggi_mendatang = df_ff[
            (df_ff["Dampak"] == "High") & (df_ff["Waktu"] >= sekarang)
        ]
    if not dampak_tinggi_mendatang.empty:
        ev = dampak_tinggi_mendatang.iloc[0]
        bendera = BENDERA_MATA_UANG.get(ev["MataUang"], "")
        st.markdown(
            f"""
            <div class="sorotan-card">
                <div class="label">★★★ Rilis Dampak Tertinggi Berikutnya</div>
                <div class="judul">{bendera} {ev['Event']}</div>
                <div class="sub">{ev['Waktu'].strftime('%A, %d %b %Y — %H:%M WIB')}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div class="sorotan-card">
                <div class="label">★★★ Rilis Dampak Tertinggi Berikutnya</div>
                <div class="judul">Tidak ada tersisa dalam periode "{periode_dipilih}"</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.markdown("---")

# ============================================================
# 6. Sidebar — filter tambahan (mata uang, dampak, kata kunci)
# ============================================================
if not df_ff.empty:
    daftar_mata_uang = sorted(df_ff["MataUang"].dropna().unique().tolist())
else:
    daftar_mata_uang = []

mata_uang_dipilih = st.sidebar.multiselect(
    "Mata uang / negara",
    options=daftar_mata_uang,
    default=[m for m in ["USD", "EUR", "GBP", "JPY", "CNY"] if m in daftar_mata_uang] or daftar_mata_uang,
)

dampak_dipilih_label = st.sidebar.multiselect(
    "Level dampak",
    options=["★★★ Tinggi", "★★☆ Sedang", "★☆☆ Rendah"],
    default=["★★★ Tinggi", "★★☆ Sedang"],
)
PETA_LABEL_DAMPAK = {"★★★ Tinggi": "High", "★★☆ Sedang": "Medium", "★☆☆ Rendah": "Low"}
dampak_dipilih = [PETA_LABEL_DAMPAK[l] for l in dampak_dipilih_label]

hanya_event_penting = st.sidebar.checkbox(
    "Hanya tampilkan event kunci (CPI, NFP, GDP, FOMC, PMI, dll)",
    value=False,
)

kata_kunci_cari = st.sidebar.text_input("Cari event (mis. 'CPI', 'FOMC')", placeholder="Ketik kata kunci...")

# ============================================================
# 7. Terapkan filter
# ============================================================
df_tampil = df_ff.copy()

if not df_tampil.empty:
    if mata_uang_dipilih:
        df_tampil = df_tampil[df_tampil["MataUang"].isin(mata_uang_dipilih)]
    if dampak_dipilih:
        df_tampil = df_tampil[df_tampil["Dampak"].isin(dampak_dipilih)]
    if hanya_event_penting:
        pola = "|".join(KATA_KUNCI_PENTING)
        df_tampil = df_tampil[df_tampil["Event"].str.contains(pola, case=False, na=False)]
    if kata_kunci_cari:
        df_tampil = df_tampil[df_tampil["Event"].str.contains(kata_kunci_cari, case=False, na=False)]

# ============================================================
# 8. Tabel kalender — dikelompokkan per hari
# ============================================================
st.subheader(f"Jadwal — {periode_dipilih}")

if df_ff.empty:
    st.info("Data kalender belum tersedia. Coba klik 'Refresh Data' di atas.")
elif df_tampil.empty:
    st.info("Tidak ada event yang cocok dengan filter yang dipilih.")
else:
    df_tampil = df_tampil.copy()
    df_tampil["_tanggal"] = df_tampil["Waktu"].dt.date

    for tanggal, grup in df_tampil.groupby("_tanggal"):
        label_tanggal = grup["Waktu"].iloc[0].strftime("%A, %d %B %Y")
        with st.expander(f"{label_tanggal}  ·  {len(grup)} event", expanded=(tanggal == sekarang.date())):
            for _, ev in grup.iterrows():
                bendera = BENDERA_MATA_UANG.get(ev["MataUang"], "")
                bintang_html = render_bintang(ev["Dampak"])
                forecast = ev["Forecast"] if ev["Forecast"] else "–"
                previous = ev["Previous"] if ev["Previous"] else "–"
                st.markdown(
                    f"""
                    <div class="event-row">
                        <div class="waktu">{ev['Waktu'].strftime('%H:%M')}</div>
                        <div class="mata-uang">{bendera} {ev['MataUang']}</div>
                        <div class="judul-event">{ev['Event']} {bintang_html}</div>
                        <div class="angka">F: {forecast}</div>
                        <div class="angka">P: {previous}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    st.caption(
        "Waktu ditampilkan dalam WIB (Asia/Jakarta). Bintang menunjukkan level dampak "
        "(★☆☆ rendah, ★★☆ sedang, ★★★ tinggi), persis seperti ikon dampak di ForexFactory. "
        "F = Forecast (perkiraan konsensus), P = Previous (angka periode sebelumnya)."
    )

st.markdown("---")

# ============================================================
# 9. Jadwal Review Indeks (MSCI)
# ============================================================
st.subheader("Jadwal Review Indeks MSCI")
st.caption(
    "MSCI mengumumkan jadwal 8 review indeks reguler berikutnya (Quarterly & Semi-Annual Index Review) "
    "setiap kali sebuah review dilakukan. Data ini bersumber langsung dari rilis resmi msci.com, "
    "bukan dari ForexFactory — ForexFactory tidak menyediakan jadwal rebalancing indeks."
)

if df_msci.empty:
    st.info("Jadwal review MSCI belum tersedia. Coba klik 'Refresh Data' di atas.")
else:
    df_msci_tampil = df_msci[["Kuartal", "Event", "Tanggal Pengumuman", "Tanggal Efektif"]].copy()
    st.dataframe(df_msci_tampil, use_container_width=True, hide_index=True)
    st.caption(
        "Semi-Annual Index Review (Mei & November) biasanya membawa perubahan komposisi indeks yang "
        "lebih besar dibanding Quarterly Index Review (Februari & Agustus). MSCI berhak mengubah "
        "tanggal-tanggal ini dengan pemberitahuan sebelumnya."
    )