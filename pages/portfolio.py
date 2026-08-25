import os
from pathlib import Path
from datetime import date

import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

try:
    from curl_cffi import requests as curl_requests
    CURL_CFFI_TERSEDIA = True
except ImportError:
    CURL_CFFI_TERSEDIA = False

try:
    import google.generativeai as genai
    GEMINI_TERSEDIA = True
except ImportError:
    GEMINI_TERSEDIA = False

# ============================================================
# 1. Konfigurasi Halaman
# ============================================================
st.set_page_config(page_title="Portfolio Tracker", layout="wide", page_icon="briefcase")
st.title("Portfolio Tracker")
st.caption("Catat saham yang kamu beli, lalu pantau nilai portofolio & untung/rugi berdasarkan harga terkini.")

# ============================================================
# 2. Styling — konsisten dengan tema di halaman utama
# ============================================================
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, .stApp, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }
    /* Cegah scroll horizontal — panel Asisten AI yang digeser ke luar layar
       (translateX) tetap dihitung lebarnya oleh browser kalau ini tidak dikunci.
       Ditarget ke beberapa kemungkinan container scroll Streamlit sekaligus. */
    html {
        overflow-x: hidden !important;
        max-width: 100vw !important;
        background-color: #0e1117 !important;
        color-scheme: dark;
    }
    body {
        overflow-x: hidden !important;
        background-color: #0e1117 !important;
        overscroll-behavior-y: none; /* cegah flash putih pas rubber-band scroll di iOS/Android */
    }
    .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    [data-testid="stMainBlockContainer"],
    .main,
    section.main {
        overflow-x: hidden !important;
        max-width: 100vw !important;
        background-color: #0e1117 !important;
    }
    [data-testid="stSidebar"] {
        background-color: #131722 !important;
    }
    #MainMenu, footer, [data-testid="stDecoration"] { visibility: hidden; height: 0; }
    h1 { font-weight: 700; letter-spacing: -0.02em; }
    h2, h3 { font-weight: 600; letter-spacing: -0.01em; }
    .stButton > button, .stDownloadButton > button {
        background-color: rgba(255,255,255,0.04);
        color: #e6e6e6;
        border-radius: 8px;
        border: 1px solid rgba(128,128,128,0.25);
        font-weight: 500;
        transition: all 0.15s ease;
    }
    .stButton > button:hover, .stDownloadButton > button:hover {
        border-color: #2962ff;
        color: #2962ff;
    }
    .stButton > button:disabled {
        background-color: rgba(255,255,255,0.02);
        color: rgba(255,255,255,0.35) !important;
    }

    /* Expander — background gelap (bawaannya putih kalau tidak di-set) */
    [data-testid="stExpander"] {
        background-color: rgba(255,255,255,0.02);
        border: 1px solid rgba(128,128,128,0.15);
        border-radius: 10px;
    }
    [data-testid="stExpander"] summary {
        background-color: transparent !important;
    }

    /* Input, selectbox, multiselect — background gelap konsisten (BaseWeb default-nya putih) */
    .stTextInput input,
    .stNumberInput input,
    .stDateInput input,
    .stSelectbox > div > div,
    .stMultiSelect > div > div,
    [data-baseweb="select"] > div,
    [data-baseweb="input"] {
        background-color: rgba(255,255,255,0.04) !important;
        color: #e6e6e6 !important;
        border-radius: 8px !important;
        border-color: rgba(128,128,128,0.25) !important;
    }
    [data-baseweb="tag"] {
        background-color: rgba(41,98,255,0.25) !important;
    }

    /* Menu dropdown/popover BaseWeb dirender di luar pohon DOM utama (portal ke
       document.body), jadi harus ditarget terpisah supaya ikut gelap juga. */
    [data-baseweb="popover"],
    [data-baseweb="menu"],
    ul[role="listbox"],
    li[role="option"] {
        background-color: #131722 !important;
        color: #e6e6e6 !important;
    }
    li[role="option"]:hover {
        background-color: rgba(255,255,255,0.08) !important;
    }

    *, *::before, *::after {
        box-sizing: border-box;
    }

    @media (max-width: 768px) {
        [data-testid="stMainBlockContainer"], .main .block-container {
            padding-left: 1rem !important;
        }

        /* Streamlit otomatis nge-stack st.columns() ke bawah kalau layar
           sempit — di sini dipaksa TETAP sejajar (nowrap) dan boleh
           discroll ke samping, bukan ditumpuk ke bawah semua. */
        [data-testid="stHorizontalBlock"] {
            flex-wrap: nowrap !important;
            overflow-x: auto !important;
            -webkit-overflow-scrolling: touch;
        }
        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
        [data-testid="stHorizontalBlock"] > [data-testid="column"] {
            flex: 0 0 auto !important;
            width: auto !important;
            min-width: 200px;
        }

        [data-testid="stDataFrame"],
        [data-testid="stImage"],
        iframe,
        .element-container {
            max-width: 100% !important;
        }

        h1 { font-size: 1.6rem !important; }
        h2 { font-size: 1.25rem !important; }

        .ringkasan-modal-grid {
            grid-template-columns: repeat(2, 1fr) !important;
        }
    }
    [data-testid="stHorizontalBlock"], [data-testid="stDataFrame"] {
        -webkit-overflow-scrolling: touch;
        scroll-behavior: smooth;
    }
    [data-testid="stExpander"] { border: 1px solid rgba(128,128,128,0.15); border-radius: 10px; }
    [data-testid="stMetricValue"] { font-weight: 700; }

    /* Kartu ringkasan modal & ekuitas — grid 3 kolom x 2 baris ala platform
       trading (Trading Balance, Invested, Open / P&L, Gain, Total Equity). */
    .ringkasan-modal-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 22px 16px;
        background-color: #161b26;
        border: 1px solid rgba(151, 166, 195, 0.30);
        border-radius: 12px;
        padding: 22px 24px;
    }
    .ringkasan-modal-grid .stat .nilai {
        font-size: 26px;
        font-weight: 800;
        letter-spacing: -0.01em;
        color: #e6e6e6;
        white-space: nowrap;
    }
    .ringkasan-modal-grid .stat .label {
        font-size: 13px;
        color: #8a8f99;
        margin-top: 2px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# 2b. Asisten AI — pengaturan API key (session_state dibagi lintas halaman)
# ============================================================
with st.sidebar.expander("Asisten AI", expanded=False):
    if not GEMINI_TERSEDIA:
        st.caption("Fitur ini butuh package `google-generativeai`. Install dengan: `pip install google-generativeai`")
    else:
        st.caption(
            "Masukkan API key Gemini sendiri untuk mengaktifkan asisten AI (ada tier gratis). "
            "API key hanya disimpan selama sesi berjalan."
        )
        st.session_state["gemini_api_key"] = st.text_input(
            "API Key Gemini",
            type="password",
            value=st.session_state.get("gemini_api_key", ""),
            placeholder="AIza...",
            key="input_gemini_api_key_pf",
        )
        st.session_state["model_ai"] = st.text_input(
            "Model",
            value=st.session_state.get("model_ai", "gemini-3.6-flash"),
            key="input_model_ai_pf",
        )
        st.caption("Dapatkan API key gratis di aistudio.google.com/apikey")

if "tampilkan_panel_ai" not in st.session_state:
    st.session_state.tampilkan_panel_ai = False
with st.sidebar.container(border=True):
    st.session_state.tampilkan_panel_ai = st.checkbox(
        "Tampilkan panel Asisten AI di sisi kanan",
        value=st.session_state.tampilkan_panel_ai,
        key="toggle_panel_ai_pf",
    )


def dapatkan_model_ai(system_prompt: str):
    api_key = st.session_state.get("gemini_api_key", "")
    if not GEMINI_TERSEDIA or not api_key:
        return None
    try:
        genai.configure(api_key=api_key)
        return genai.GenerativeModel(
            model_name=st.session_state.get("model_ai", "gemini-3.6-flash"),
            system_instruction=system_prompt,
        )
    except Exception:
        return None


def tanya_ai(system_prompt: str, riwayat_chat: list) -> str:
    model = dapatkan_model_ai(system_prompt)
    if model is None:
        return (
            "Asisten AI belum aktif. Masukkan API key Gemini di sidebar (bagian 'Asisten AI') "
            "terlebih dahulu — atau install `pip install google-generativeai` kalau belum terpasang."
        )
    try:
        riwayat_gemini = [
            {"role": "user" if m["role"] == "user" else "model", "parts": [m["content"]]}
            for m in riwayat_chat[:-1]
        ]
        sesi = model.start_chat(history=riwayat_gemini)
        respon = sesi.send_message(riwayat_chat[-1]["content"], request_options={"timeout": 30})
        return respon.text
    except Exception as e:
        return f"Terjadi error saat memanggil AI: {e}"


# ============================================================
# 3. Path data — daftar saham IDX, file portofolio, & memori Asisten AI
#    Semuanya diletakkan satu folder dengan file utama (bukan di dalam pages/).
# ============================================================
BASE_DIR = Path(__file__).resolve().parent.parent
BASE_DIR.mkdir(parents=True, exist_ok=True)


@st.cache_resource(show_spinner=False)
def dapatkan_sesi_yf():
    """Session yang 'menyamar' sebagai browser Chrome asli — Yahoo Finance
    sering memblokir request dari server cloud, session ini mengurangi
    kemungkinan itu terjadi."""
    if not CURL_CFFI_TERSEDIA:
        return None
    try:
        return curl_requests.Session(impersonate="chrome")
    except Exception:
        return None
PATH_CSV_SAHAM = BASE_DIR / "daftar_saham_idx.csv"
PATH_PORTOFOLIO = BASE_DIR / "portofolio.csv"
PATH_MEMORI_AI_PF = BASE_DIR / "memori_ai_portofolio.json"

KOLOM_PORTOFOLIO = ["Ticker", "Jumlah", "HargaBeli", "TanggalBeli"]


def muat_memori_ai_pf():
    if PATH_MEMORI_AI_PF.exists():
        try:
            import json
            with open(PATH_MEMORI_AI_PF, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"riwayat": [], "catatan_preferensi": ""}
    return {"riwayat": [], "catatan_preferensi": ""}


def simpan_memori_ai_pf(riwayat: list, catatan_preferensi: str):
    try:
        import json
        with open(PATH_MEMORI_AI_PF, "w", encoding="utf-8") as f:
            json.dump({"riwayat": riwayat, "catatan_preferensi": catatan_preferensi}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # gagal simpan bukan hal fatal, chat tetap jalan normal di sesi ini


# ============================================================
# 2c. Asisten AI — konteks & prompt sistem (dipakai panel di bagian paling bawah)
# ============================================================
SYSTEM_PROMPT_PORTOFOLIO = """Kamu adalah asisten manajemen portofolio di dalam sebuah aplikasi portfolio tracker. Tugasmu membantu pengguna memahami komposisi dan performa portofolio saham mereka.

Data portofolio pengguna saat ini:
{konteks}
{blok_preferensi}
{blok_dokumen}
Instruksi:
- Jawab berdasarkan data di atas, jangan mengarang angka yang tidak ada.
- Perhatikan konsentrasi/diversifikasi portofolio — kalau porsi satu saham terlalu dominan, sebutkan risikonya.
- Boleh membahas performa tiap posisi (untung/rugi), tapi jangan pernah memberi instruksi mutlak seperti "jual semua" atau "beli lagi" tanpa menjelaskan trade-off dan risikonya.
- Ini BUKAN nasihat keuangan resmi — selalu ingatkan bahwa keputusan akhir ada di tangan pengguna.
- Kalau ada catatan preferensi pengguna di atas, sesuaikan gaya jawabanmu dengan itu.
- Jawab dalam Bahasa Indonesia, ringkas, boleh pakai bullet point.
"""


def bangun_konteks_portofolio(baris_tampil, total_modal, total_nilai_sekarang, saldo_tersedia=0.0, total_equity=0.0):
    if not baris_tampil:
        return (
            f"Portofolio belum ada posisi saham. Trading Balance (kas belum diinvestasikan): "
            f"Rp {saldo_tersedia:,.0f}."
        )
    baris_teks = [
        f"- {item['Ticker']} ({item['Nama']}): {item['Jumlah']:,.0f} lembar, "
        f"harga beli {item['Harga Beli']:,.0f}, harga sekarang {item['Harga Sekarang']}, "
        f"nilai sekarang {item['Nilai Sekarang']}, untung/rugi {item['Untung/Rugi']} ({item['Persentase']})"
        for item in baris_tampil
    ]
    ringkasan = (
        f"Trading Balance (kas belum diinvestasikan): Rp {saldo_tersedia:,.0f}. "
        f"Invested (modal di posisi terbuka): Rp {total_modal:,.0f}. "
        f"Nilai posisi saat ini: Rp {total_nilai_sekarang:,.0f}. "
        f"Total Equity (kas + nilai posisi): Rp {total_equity:,.0f}."
    )
    return ringkasan + "\n" + "\n".join(baris_teks)


if "riwayat_chat_portofolio" not in st.session_state:
    memori_awal_pf = muat_memori_ai_pf()
    st.session_state.riwayat_chat_portofolio = memori_awal_pf["riwayat"]
    st.session_state.catatan_preferensi_ai_pf = memori_awal_pf["catatan_preferensi"]

if "catatan_preferensi_ai_pf" not in st.session_state:
    st.session_state.catatan_preferensi_ai_pf = ""

SARAN_PROMPT_AI_PF = [
    ("📊", "Apakah portofolio saya terlalu terkonsentrasi?"),
    ("📈", "Bagaimana performa portofolio saya sejauh ini?"),
    ("⚠️", "Saham mana yang risikonya paling besar?"),
    ("🧭", "Bagaimana cara diversifikasi yang lebih baik?"),
]


def _escape_dolar(teks: str) -> str:
    """Escape tanda '$' supaya Streamlit tidak salah mengira itu sebagai
    pembuka rumus LaTeX."""
    return teks.replace("$", "\\$")


def _proses_prompt_ai_pf(kotak_chat, prompt_teks: str, konteks_pf: str):
    """Kirim satu prompt ke AI, tampilkan langsung di kotak chat, dan simpan ke riwayat (+ memori permanen)."""
    st.session_state.riwayat_chat_portofolio.append({"role": "user", "content": prompt_teks})
    with kotak_chat:
        with st.chat_message("user"):
            st.markdown(prompt_teks)
        with st.chat_message("assistant"):
            with st.spinner("Menganalisis..."):
                catatan = st.session_state.get("catatan_preferensi_ai_pf", "").strip()
                blok_preferensi = f"\nCatatan preferensi pengguna (ikuti gaya ini):\n{catatan}\n" if catatan else ""

                dok = st.session_state.get("dokumen_diupload_ai_pf", "").strip()
                blok_dokumen = f"\nData/dokumen tambahan yang diupload pengguna:\n{dok[:6000]}\n" if dok else ""

                jawaban = tanya_ai(
                    SYSTEM_PROMPT_PORTOFOLIO.format(
                        konteks=konteks_pf, blok_preferensi=blok_preferensi, blok_dokumen=blok_dokumen,
                    ),
                    st.session_state.riwayat_chat_portofolio,
                )
            st.markdown(_escape_dolar(jawaban))
    st.session_state.riwayat_chat_portofolio.append({"role": "assistant", "content": jawaban})
    simpan_memori_ai_pf(st.session_state.riwayat_chat_portofolio, st.session_state.get("catatan_preferensi_ai_pf", ""))


@st.cache_data(show_spinner=False)
def muat_daftar_saham_idx():
    if not PATH_CSV_SAHAM.exists():
        return pd.DataFrame(columns=["Kode", "Nama Perusahaan", "Kategori", "Ticker"])
    df = pd.read_csv(PATH_CSV_SAHAM)
    df["Kode"] = df["Kode"].astype(str).str.strip()
    df["Nama Perusahaan"] = df["Nama Perusahaan"].astype(str).str.strip()
    df["Ticker"] = df["Kode"] + ".JK"
    return df


df_idx = muat_daftar_saham_idx()
LABEL_SEMUA_SAHAM = (
    [f"{kode} — {nama}" for kode, nama in zip(df_idx["Ticker"], df_idx["Nama Perusahaan"])]
    if not df_idx.empty else []
)


def muat_portofolio():
    if PATH_PORTOFOLIO.exists():
        try:
            df = pd.read_csv(PATH_PORTOFOLIO)
            for kolom in KOLOM_PORTOFOLIO:
                if kolom not in df.columns:
                    df[kolom] = None
            return df[KOLOM_PORTOFOLIO]
        except Exception:
            return pd.DataFrame(columns=KOLOM_PORTOFOLIO)
    return pd.DataFrame(columns=KOLOM_PORTOFOLIO)


def simpan_portofolio(df: pd.DataFrame):
    try:
        df.to_csv(PATH_PORTOFOLIO, index=False)
    except Exception as e:
        st.warning(f"Gagal menyimpan portofolio ke file ({e}) — perubahan tetap berlaku untuk sesi ini saja.")


if "portofolio" not in st.session_state:
    st.session_state.portofolio = muat_portofolio()


# ============================================================
# 5c. Ledger Modal — mencatat semua pergerakan kas: setor, tarik, beli, jual.
#     Saldo Trading Balance = jumlah semua baris ledger (positif = kas masuk,
#     negatif = kas keluar). Ini yang menentukan berapa "amunisi" tersisa
#     buat beli saham baru.
# ============================================================
PATH_LEDGER_MODAL = BASE_DIR / "ledger_modal.csv"
KOLOM_LEDGER = ["Tanggal", "Jenis", "Keterangan", "Jumlah"]


def muat_ledger_modal():
    if PATH_LEDGER_MODAL.exists():
        try:
            df = pd.read_csv(PATH_LEDGER_MODAL)
            for kolom in KOLOM_LEDGER:
                if kolom not in df.columns:
                    df[kolom] = None
            return df[KOLOM_LEDGER]
        except Exception:
            return pd.DataFrame(columns=KOLOM_LEDGER)
    return pd.DataFrame(columns=KOLOM_LEDGER)


def simpan_ledger_modal(df: pd.DataFrame):
    try:
        df.to_csv(PATH_LEDGER_MODAL, index=False)
    except Exception as e:
        st.warning(f"Gagal menyimpan riwayat modal ke file ({e}) — perubahan tetap berlaku untuk sesi ini saja.")


def catat_transaksi_modal(jenis: str, keterangan: str, jumlah: float):
    """jumlah positif = kas masuk (setor, jual, koreksi hapus), negatif = kas keluar (tarik, beli)."""
    baris_baru = pd.DataFrame([{
        "Tanggal": date.today().isoformat(),
        "Jenis": jenis,
        "Keterangan": keterangan,
        "Jumlah": jumlah,
    }])
    st.session_state.ledger_modal = pd.concat([st.session_state.ledger_modal, baris_baru], ignore_index=True)
    simpan_ledger_modal(st.session_state.ledger_modal)


if "ledger_modal" not in st.session_state:
    st.session_state.ledger_modal = muat_ledger_modal()


def hitung_saldo_tersedia() -> float:
    if st.session_state.ledger_modal.empty:
        return 0.0
    return float(st.session_state.ledger_modal["Jumlah"].sum())


def render_kartu_ringkasan_modal(saldo_tersedia, invested, jumlah_posisi, pnl, persen_gain, total_equity):
    """Kartu ringkasan gaya platform trading: grid 3 kolom x 2 baris —
    Trading Balance / Invested / Open (baris 1), P&L / Gain / Total Equity
    (baris 2). P&L & Gain diwarnai hijau/merah sesuai tandanya."""
    warna_pnl = "#26a69a" if pnl >= 0 else "#ef5350"
    warna_gain = "#26a69a" if persen_gain >= 0 else "#ef5350"
    tanda_pnl = "+" if pnl >= 0 else ""
    tanda_gain = "+" if persen_gain >= 0 else ""

    st.markdown(
        f"""
        <div class="ringkasan-modal-grid">
            <div class="stat"><div class="nilai">{saldo_tersedia:,.0f}</div><div class="label">Trading Balance</div></div>
            <div class="stat"><div class="nilai">{invested:,.0f}</div><div class="label">Invested</div></div>
            <div class="stat"><div class="nilai">{jumlah_posisi:,.0f}</div><div class="label">Open</div></div>
            <div class="stat"><div class="nilai" style="color:{warna_pnl};">{tanda_pnl}{pnl:,.0f}</div><div class="label">P&amp;L</div></div>
            <div class="stat"><div class="nilai" style="color:{warna_gain};">{tanda_gain}{persen_gain:.2f}%</div><div class="label">Gain</div></div>
            <div class="stat"><div class="nilai">{total_equity:,.0f}</div><div class="label">Total Equity</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# 4. Fetch harga terkini (cache 10 menit)
# ============================================================
@st.cache_data(ttl=600, show_spinner=False)
def ambil_harga_terkini(ticker: str):
    try:
        info = yf.Ticker(ticker, session=dapatkan_sesi_yf()).info
        harga = info.get("currentPrice") or info.get("regularMarketPrice")
        nama = info.get("shortName", ticker)
        mata_uang = info.get("currency", "")
        return harga, nama, mata_uang
    except Exception:
        return None, ticker, ""


# ============================================================
# 4b. Grafik Performa — rekonstruksi kurva ekuitas harian dari histori
#    harga tiap saham (yfinance) + tanggal beli tiap posisi + mutasi
#    ledger, dan kurva IHSG buat pembanding.
# ============================================================
IHSG_TICKER = "^JKSE"

RENTANG_WAKTU_HARI = {"1W": 7, "1M": 30, "3M": 90, "1Y": 365}


@st.cache_data(ttl=3600, show_spinner=False)
def ambil_histori_harga(ticker: str):
    """Histori harga penutupan harian ~5 tahun terakhir (cukup buat cover
    rentang 'All' di kebanyakan kasus pemakaian pribadi)."""
    try:
        data = yf.Ticker(ticker, session=dapatkan_sesi_yf()).history(period="5y")
        if data is None or data.empty:
            return None
        harga = data["Close"]
        if harga.index.tz is not None:
            harga.index = harga.index.tz_localize(None)
        return harga
    except Exception:
        return None


def bangun_kurva_ekuitas(portofolio_df: pd.DataFrame, ledger_df: pd.DataFrame) -> pd.Series:
    """Rekonstruksi Total Equity (kas + nilai posisi) per hari, dari
    tanggal transaksi/posisi paling awal sampai hari ini."""
    tanggal_mulai_kandidat = []
    if not portofolio_df.empty:
        tanggal_mulai_kandidat.append(pd.to_datetime(portofolio_df["TanggalBeli"]).min())
    if not ledger_df.empty:
        tanggal_mulai_kandidat.append(pd.to_datetime(ledger_df["Tanggal"]).min())

    if not tanggal_mulai_kandidat:
        return pd.Series(dtype=float)

    tanggal_mulai = min(tanggal_mulai_kandidat)
    tanggal_akhir = pd.Timestamp(date.today())
    indeks_tanggal = pd.date_range(tanggal_mulai, tanggal_akhir, freq="D")

    nilai_posisi = pd.Series(0.0, index=indeks_tanggal)
    if not portofolio_df.empty:
        for ticker, grup in portofolio_df.groupby("Ticker"):
            harga = ambil_histori_harga(ticker)
            if harga is None:
                continue
            harga_harian = harga.reindex(indeks_tanggal).ffill().bfill()

            lembar_kumulatif = pd.Series(0.0, index=indeks_tanggal)
            for _, baris in grup.iterrows():
                tgl_beli = pd.to_datetime(baris["TanggalBeli"])
                lembar_kumulatif.loc[lembar_kumulatif.index >= tgl_beli] += float(baris["Jumlah"])

            nilai_posisi = nilai_posisi.add(lembar_kumulatif * harga_harian, fill_value=0.0)

    kas = pd.Series(0.0, index=indeks_tanggal)
    if not ledger_df.empty:
        for _, baris in ledger_df.iterrows():
            tgl = pd.to_datetime(baris["Tanggal"])
            kas.loc[kas.index >= tgl] += float(baris["Jumlah"])

    return (nilai_posisi + kas).round(0)


def potong_rentang_waktu(seri: pd.Series, label: str) -> pd.Series:
    if seri.empty:
        return seri
    akhir = seri.index.max()
    if label == "All":
        return seri
    if label == "YTD":
        mulai = pd.Timestamp(year=akhir.year, month=1, day=1)
    else:
        mulai = akhir - pd.Timedelta(days=RENTANG_WAKTU_HARI[label])
    return seri[seri.index >= mulai]


def hitung_kurva_return_persen(seri: pd.Series) -> pd.Series:
    if seri.empty:
        return seri
    dasar = seri.iloc[0]
    if not dasar:
        return seri * 0.0
    return (seri / dasar - 1) * 100


def render_grafik_performa(seri_ekuitas: pd.Series):
    st.subheader("Performance")

    if seri_ekuitas.empty:
        st.caption(
            "Grafik performa portofolio dari hari ke hari akan muncul di sini setelah kamu "
            "menyetor modal dan/atau menambahkan saham."
        )
        st.markdown("---")
        return

    rentang = st.radio(
        "Rentang waktu grafik performa", ["1W", "1M", "3M", "YTD", "1Y", "All"],
        index=3, horizontal=True, key="rentang_grafik_ekuitas", label_visibility="collapsed",
    )
    seri_tampil = potong_rentang_waktu(seri_ekuitas, rentang)

    if seri_tampil.empty:
        st.caption("Belum ada data untuk rentang waktu ini.")
        st.markdown("---")
        return

    nilai_awal = seri_tampil.iloc[0]
    nilai_akhir = seri_tampil.iloc[-1]
    perubahan = nilai_akhir - nilai_awal
    persen = (perubahan / nilai_awal * 100) if nilai_awal else 0.0
    naik = perubahan >= 0
    warna = "#26a69a" if naik else "#ef5350"
    tanda = "+" if naik else ""

    st.markdown(
        f"""
        <div style="margin-bottom:4px;">
            <div style="font-size:13px; color:#8a8f99;">Total Equity</div>
            <div style="font-size:32px; font-weight:800; letter-spacing:-0.02em;">
                Rp {nilai_akhir:,.0f}
            </div>
            <div style="font-size:14px; font-weight:600; color:{warna};">
                {tanda}{perubahan:,.0f} ({tanda}{persen:.2f}%) &nbsp;<span style="color:#8a8f99; font-weight:400;">periode {rentang}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=seri_tampil.index, y=seri_tampil.values, mode="lines",
        line=dict(color=warna, width=2),
        fill="tozeroy", fillcolor=f"{warna}26",
        hovertemplate="%{x|%d %b %Y}<br>Rp %{y:,.0f}<extra></extra>",
    ))
    fig.update_layout(
        height=260, margin=dict(l=10, r=10, t=10, b=10),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False, color="#8a8f99"),
        yaxis=dict(showgrid=True, gridcolor="rgba(151,166,195,0.15)", color="#8a8f99"),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)
    st.markdown("---")


def render_grafik_perbandingan_ihsg(seri_ekuitas: pd.Series):
    st.subheader("Perbandingan dengan IHSG")
    st.caption(
        "Membandingkan persentase pertumbuhan Total Equity portofolio kamu dengan IDX Composite "
        "(IHSG) pada rentang waktu yang sama. Data IHSG dari Yahoo Finance."
    )

    if seri_ekuitas.empty:
        st.caption("Grafik perbandingan akan muncul di sini setelah kamu punya data portofolio.")
        return

    ihsg = ambil_histori_harga(IHSG_TICKER)
    if ihsg is None:
        st.warning("Gagal mengambil data IHSG dari Yahoo Finance. Coba lagi nanti.")
        return

    rentang = st.radio(
        "Rentang waktu grafik perbandingan IHSG", ["1W", "1M", "3M", "YTD", "1Y", "All"],
        index=3, horizontal=True, key="rentang_grafik_ihsg", label_visibility="collapsed",
    )

    seri_ekuitas_potong = potong_rentang_waktu(seri_ekuitas, rentang)
    if seri_ekuitas_potong.empty:
        st.caption("Belum ada data untuk rentang waktu ini.")
        return

    ihsg_potong = ihsg.reindex(seri_ekuitas_potong.index).ffill().bfill()

    return_porto = hitung_kurva_return_persen(seri_ekuitas_potong)
    return_ihsg = hitung_kurva_return_persen(ihsg_potong)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            f'<div style="border-left:3px solid #26a69a; padding-left:10px;">'
            f'<div style="color:#8a8f99; font-size:13px;">Portfolio</div>'
            f'<div style="font-size:20px; font-weight:700;">{return_porto.iloc[-1]:+.2f}%</div></div>',
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f'<div style="border-left:3px solid #a78bfa; padding-left:10px;">'
            f'<div style="color:#8a8f99; font-size:13px;">IHSG</div>'
            f'<div style="font-size:20px; font-weight:700;">{return_ihsg.iloc[-1]:+.2f}%</div></div>',
            unsafe_allow_html=True,
        )

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=return_porto.index, y=return_porto.values, mode="lines", name="Portfolio",
        line=dict(color="#26a69a", width=2),
        hovertemplate="%{x|%d %b %Y}<br>Portfolio: %{y:+.2f}%<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=return_ihsg.index, y=return_ihsg.values, mode="lines", name="IHSG",
        line=dict(color="#a78bfa", width=2),
        hovertemplate="%{x|%d %b %Y}<br>IHSG: %{y:+.2f}%<extra></extra>",
    ))
    fig.add_hline(y=0, line_dash="dot", line_color="rgba(151,166,195,0.35)")
    fig.update_layout(
        height=300, margin=dict(l=10, r=10, t=10, b=10),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        xaxis=dict(showgrid=False, color="#8a8f99"),
        yaxis=dict(showgrid=True, gridcolor="rgba(151,166,195,0.15)", color="#8a8f99", ticksuffix="%"),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)


# ============================================================
# 5. Layout dua bagian: konten utama (kiri) + panel Asisten AI (kanan, fixed sidebar)
# ============================================================
tampilkan_panel_ai = st.session_state.get("tampilkan_panel_ai", False)
LEBAR_PANEL_AI = 380  # px
PADDING_KANAN_AKTIF = LEBAR_PANEL_AI + 24 if tampilkan_panel_ai else 0

st.markdown(
    f"""
    <style>
    [data-testid="stMainBlockContainer"], .main .block-container {{
        padding-right: {PADDING_KANAN_AKTIF}px !important;
        transition: padding-right 0.18s cubic-bezier(0.2, 0, 0.2, 1);
    }}

    /* Di layar sempit (HP), panel AI jadi overlay penuh (bukan sisip di
       samping), jadi konten utama TIDAK perlu diberi ruang kosong di
       kanan — kalau tetap dipaksa, layar HP jadi kepencet sempit sekali. */
    @media (max-width: 768px) {{
        [data-testid="stMainBlockContainer"], .main .block-container {{
            padding-right: 1rem !important;
        }}
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# Backdrop khusus HP: kalau panel AI kebuka di layar sempit, area di luar
# panel jadi bisa diklik/ditap buat nutup panel-nya lagi.
components.html(
    f"""
    <script>
    (function() {{
        const parentDoc = window.parent.document;
        let backdrop = parentDoc.getElementById('ai-panel-backdrop');
        if (!backdrop) {{
            backdrop = parentDoc.createElement('div');
            backdrop.id = 'ai-panel-backdrop';
            backdrop.style.cssText = 'position:fixed; top:0; left:0; right:0; bottom:0;' +
                'background:rgba(0,0,0,0.35); z-index:999998; display:none;';
            parentDoc.body.appendChild(backdrop);
            backdrop.addEventListener('click', function() {{
                const semuaCheckbox = parentDoc.querySelectorAll('[data-testid="stCheckbox"]');
                for (const cb of semuaCheckbox) {{
                    if (cb.innerText && cb.innerText.includes('Tampilkan panel Asisten AI')) {{
                        const input = cb.querySelector('input[type="checkbox"]');
                        if (input) {{ input.click(); }}
                        break;
                    }}
                }}
            }});
        }}
        const panelTerbuka = {str(tampilkan_panel_ai).lower()};
        const layarSempit = window.parent.innerWidth <= 768;
        backdrop.style.display = (panelTerbuka && layarSempit) ? 'block' : 'none';
    }})();
    </script>
    """,
    height=0,
)

col_main = st.container()

with col_main:

    # ============================================================
    # 5a-1. Grafik Performa (Total Equity dari hari ke hari) — paling atas
    #      halaman, direkonstruksi dari histori harga tiap saham + tanggal
    #      beli + mutasi ledger. Ditaruh sebelum apa pun supaya langsung
    #      kelihatan begitu halaman dibuka.
    # ============================================================
    with st.spinner("Menghitung performa portofolio..."):
        seri_ekuitas = bangun_kurva_ekuitas(st.session_state.portofolio, st.session_state.ledger_modal)
    render_grafik_performa(seri_ekuitas)

    # ============================================================
    # 5a0. Kelola Modal — Setor / Tarik Dana. Ini yang mengisi "Trading
    #      Balance" di kartu ringkasan; tanpa ini saldo akan selalu 0.
    # ============================================================
    with st.expander("Kelola Modal (Setor / Tarik Dana)", expanded=st.session_state.ledger_modal.empty):
        st.caption(
            "Trading Balance dihitung dari catatan setor/tarik dana di sini, dikurangi biaya "
            "setiap kali kamu menambahkan saham ke portofolio (dianggap sebagai 'pembelian')."
        )
        col_setor, col_tarik = st.columns(2)
        with col_setor:
            jumlah_setor = st.number_input("Jumlah setor", min_value=0.0, step=100000.0, value=0.0, key="input_setor")
            if st.button("Setor Dana", use_container_width=True) and jumlah_setor > 0:
                catat_transaksi_modal("Setor", "Setor dana", jumlah_setor)
                st.rerun()
        with col_tarik:
            jumlah_tarik = st.number_input("Jumlah tarik", min_value=0.0, step=100000.0, value=0.0, key="input_tarik")
            if st.button("Tarik Dana", use_container_width=True) and jumlah_tarik > 0:
                catat_transaksi_modal("Tarik", "Tarik dana", -jumlah_tarik)
                st.rerun()

        if not st.session_state.ledger_modal.empty:
            with st.expander("Riwayat mutasi modal", expanded=False):
                st.dataframe(
                    st.session_state.ledger_modal.sort_index(ascending=False),
                    use_container_width=True, hide_index=True,
                )

    # ============================================================
    # 5a. Form tambah kepemilikan baru
    # ============================================================
    with st.expander("Tambah Saham ke Portofolio", expanded=st.session_state.portofolio.empty):
        mode_input = st.radio("Cara pilih saham", ["Pilih dari daftar IDX", "Ketik manual (termasuk saham luar negeri)"], horizontal=True)

        if mode_input == "Pilih dari daftar IDX":
            pilihan_label = st.selectbox("Saham", LABEL_SEMUA_SAHAM, index=None, placeholder="Ketik nama atau kode untuk mencari...")
            ticker_baru = pilihan_label.split(" — ")[0] if pilihan_label else None
        else:
            ticker_baru = st.text_input("Kode ticker", placeholder="mis. BBCA.JK atau AAPL")

        col1, col2, col3 = st.columns(3)
        with col1:
            jumlah_baru = st.number_input("Jumlah lembar saham", min_value=0, step=1, value=0)
        with col2:
            harga_beli_baru = st.number_input("Harga beli per lembar", min_value=0.0, step=1.0, value=0.0)
        with col3:
            tanggal_beli_baru = st.date_input("Tanggal beli", value=date.today())

        if st.button("Tambah ke Portofolio", type="primary"):
            if not ticker_baru:
                st.warning("Pilih atau ketik kode saham terlebih dahulu.")
            elif jumlah_baru <= 0 or harga_beli_baru <= 0:
                st.warning("Jumlah lembar dan harga beli harus lebih dari 0.")
            else:
                ticker_final = ticker_baru.strip().upper()
                baris_baru = pd.DataFrame([{
                    "Ticker": ticker_final,
                    "Jumlah": jumlah_baru,
                    "HargaBeli": harga_beli_baru,
                    "TanggalBeli": tanggal_beli_baru.isoformat(),
                }])
                st.session_state.portofolio = pd.concat([st.session_state.portofolio, baris_baru], ignore_index=True)
                simpan_portofolio(st.session_state.portofolio)
                catat_transaksi_modal("Beli", f"Beli {ticker_final}", -(jumlah_baru * harga_beli_baru))
                st.rerun()

    st.markdown("---")

    # ============================================================
    # 5b. Ringkasan & tabel portofolio
    # ============================================================
    portofolio = st.session_state.portofolio

    # Nilai default dipakai panel Asisten AI & kartu ringkasan walau
    # portofolio masih kosong (Trading Balance tetap relevan meski belum
    # ada posisi terbuka).
    baris_tampil = []
    total_modal = 0.0
    total_nilai_sekarang = 0.0

    if not portofolio.empty:
        with st.spinner("Mengambil harga terkini..."):
            for i, baris in portofolio.iterrows():
                ticker = baris["Ticker"]
                jumlah = float(baris["Jumlah"])
                harga_beli = float(baris["HargaBeli"])
                harga_sekarang, nama_saham, mata_uang = ambil_harga_terkini(ticker)

                modal = jumlah * harga_beli
                nilai_sekarang = jumlah * harga_sekarang if harga_sekarang else None
                untung_rugi = (nilai_sekarang - modal) if nilai_sekarang is not None else None
                persen = (untung_rugi / modal * 100) if untung_rugi is not None and modal else None

                total_modal += modal
                if nilai_sekarang is not None:
                    total_nilai_sekarang += nilai_sekarang

                baris_tampil.append({
                    "_index": i,
                    "Ticker": ticker,
                    "Nama": nama_saham,
                    "Jumlah": jumlah,
                    "Harga Beli": harga_beli,
                    "Harga Sekarang": harga_sekarang if harga_sekarang else "N/A",
                    "Modal": modal,
                    "Nilai Sekarang": nilai_sekarang if nilai_sekarang is not None else "N/A",
                    "Untung/Rugi": untung_rugi if untung_rugi is not None else "N/A",
                    "Persentase": f"{persen:.2f}%" if persen is not None else "N/A",
                    "Tanggal Beli": baris["TanggalBeli"],
                })

    saldo_tersedia = hitung_saldo_tersedia()
    total_untung_rugi = total_nilai_sekarang - total_modal
    total_persen = (total_untung_rugi / total_modal * 100) if total_modal else 0.0
    total_equity = saldo_tersedia + total_nilai_sekarang

    render_kartu_ringkasan_modal(
        saldo_tersedia=saldo_tersedia,
        invested=total_modal,
        jumlah_posisi=len(baris_tampil),
        pnl=total_untung_rugi,
        persen_gain=total_persen,
        total_equity=total_equity,
    )

    if portofolio.empty:
        st.info("Portofolio masih kosong. Tambahkan saham lewat form di atas untuk mulai memantau.")
    else:
        st.markdown("---")

        col_tabel, col_pie = st.columns([2, 1])

        with col_tabel:
            st.subheader("Rincian Kepemilikan")

            def fmt_angka(v):
                return f"{v:,.0f}" if isinstance(v, (int, float)) else v

            df_tampil = pd.DataFrame(baris_tampil).drop(columns=["_index"])
            for kolom in ["Jumlah", "Harga Beli", "Harga Sekarang", "Modal", "Nilai Sekarang", "Untung/Rugi"]:
                df_tampil[kolom] = df_tampil[kolom].apply(fmt_angka)

            st.dataframe(
                df_tampil,
                use_container_width=True,
                hide_index=True,
            )

            st.caption("Hapus kepemilikan (modal pembelian akan dikembalikan otomatis ke Trading Balance):")
            for item in baris_tampil:
                c1, c2 = st.columns([5, 1])
                c1.write(f"{item['Ticker']} — {item['Jumlah']:,.0f} lembar @ {item['Harga Beli']:,.0f}")
                if c2.button("Hapus", key=f"hapus_pf_{item['_index']}"):
                    st.session_state.portofolio = st.session_state.portofolio.drop(index=item["_index"]).reset_index(drop=True)
                    simpan_portofolio(st.session_state.portofolio)
                    catat_transaksi_modal(
                        "Koreksi", f"Hapus catatan {item['Ticker']}",
                        item["Jumlah"] * item["Harga Beli"],
                    )
                    st.rerun()

        with col_pie:
            st.subheader("Alokasi Portofolio")
            df_pie = pd.DataFrame([
                {"Ticker": item["Ticker"], "Nilai": item["Nilai Sekarang"]}
                for item in baris_tampil if item["Nilai Sekarang"] != "N/A"
            ])

            PALET_DASAR = [
                "#8ecae6", "#ffb703", "#fb8500", "#219ebc", "#ff6b6b",
                "#a3e635", "#c77dff", "#ffafcc", "#52b788", "#e9c46a",
            ]

            warna_map = {}
            if not df_pie.empty:
                with st.expander("Warna Grafik", expanded=False):
                    for idx, tk in enumerate(df_pie["Ticker"]):
                        warna_default = PALET_DASAR[idx % len(PALET_DASAR)]
                        warna_map[tk] = st.color_picker(tk, value=warna_default, key=f"warna_pie_{tk}")

            if not df_pie.empty:
                fig = px.pie(
                    df_pie, values="Nilai", names="Ticker", hole=0.45,
                    color="Ticker", color_discrete_map=warna_map,
                )
                fig.update_traces(textposition="inside", textinfo="percent+label")
                fig.update_layout(
                    margin=dict(l=10, r=10, t=10, b=10),
                    showlegend=False,
                    height=340,
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.caption("Belum ada data nilai untuk ditampilkan.")

        if st.button("Refresh Harga Sekarang"):
            ambil_harga_terkini.clear()
            st.rerun()

    st.markdown("---")

    # ============================================================
    # 5d. Grafik Perbandingan dengan IHSG — paling bawah halaman.
    # ============================================================
    render_grafik_perbandingan_ihsg(seri_ekuitas)


# ============================================================
# 6. Asisten AI — panel fixed di sisi kanan (menyatu seperti sidebar bawaan,
#    tapi di kanan), polos tanpa efek dekoratif, sama seperti di halaman
#    Pembanding Saham.
# ============================================================
with st.container(key="panel_asisten_ai"):

        # Container ini SELALU di-render (tidak dibungkus if) supaya node-nya
        # tetap ada di DOM — buka/tutup panel cuma menggeser transform & opacity,
        # bukan memasang/melepas elemen, sehingga transisinya mulus (bukan lompat).
        _transform_panel = "translateX(0)" if tampilkan_panel_ai else "translateX(100%)"
        _opacity_panel = 1 if tampilkan_panel_ai else 0
        _pointer_panel = "auto" if tampilkan_panel_ai else "none"

        st.markdown(
            f"""
            <style>
            .st-key-panel_asisten_ai {{
                position: fixed;
                top: 0;
                right: 0;
                width: {LEBAR_PANEL_AI}px;
                height: 100vh;
                overflow-y: auto;
                background: #12161f;
                border-left: 1px solid rgba(255,255,255,0.08);
                padding: 16px;
                padding-bottom: 90px;
                z-index: 999999;
                transform: {_transform_panel};
                opacity: {_opacity_panel};
                pointer-events: {_pointer_panel};
                transition: transform 0.18s cubic-bezier(0.2, 0, 0.2, 1), opacity 0.15s ease;
                will-change: transform;
                -webkit-overflow-scrolling: touch;
            }}
            .gemini-judul {{
                font-size: 16px;
                font-weight: 600;
                color: #e6e6e6;
                margin-bottom: 2px;
            }}
            .gemini-caption {{
                font-size: 12px;
                color: #8891aa;
                line-height: 1.4;
                margin: 0 0 12px 0;
            }}
            .gemini-greeting {{
                padding: 16px 2px 4px 2px;
                color: #cfd2dc;
                font-size: 15px;
            }}
            .gemini-chip-label {{
                font-size: 11.5px;
                color: #6f7893;
                margin: 12px 2px 6px 2px;
            }}
            .st-key-panel_asisten_ai .stButton > button {{
                background: rgba(255,255,255,0.03);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 8px;
                color: #d7dcf5;
                font-size: 12.5px;
                padding: 7px 12px;
                text-align: left;
                white-space: normal;
                line-height: 1.3;
            }}
            .st-key-panel_asisten_ai .stButton > button:hover {{
                border-color: rgba(255,255,255,0.3);
                color: #ffffff;
            }}
            .st-key-panel_asisten_ai [data-testid="stChatMessage"] {{
                background: transparent;
                padding: 4px 0;
            }}
            .st-key-panel_asisten_ai [data-testid="stChatMessageContent"] {{
                background: rgba(255,255,255,0.04);
                border: 1px solid rgba(255,255,255,0.06);
                border-radius: 10px;
                padding: 10px 14px;
            }}
            /* Chat input dibiarkan mengalir normal (bukan sticky/fixed) —
               nempel di posisi paling bawah dari urutan konten panel. */
            .st-key-panel_asisten_ai [data-testid="stChatInput"] {{
                width: 100%;
                margin-top: 12px;
                background: rgba(18,22,31,0.97);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 10px;
            }}
            .st-key-panel_asisten_ai [data-testid="stChatInput"] textarea {{
                color: #eef0fb !important;
            }}

            /* Tombol close "X" — bulat kecil, nempel di pojok kanan atas panel. */
            .st-key-panel_asisten_ai .st-key-btn_tutup_panel_ai_pf button {{
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.14);
                border-radius: 50%;
                width: 32px;
                height: 32px;
                padding: 0;
                min-height: 32px;
                line-height: 1;
                font-size: 15px;
                color: #d7dcf5;
                display: flex;
                align-items: center;
                justify-content: center;
            }}
            .st-key-panel_asisten_ai .st-key-btn_tutup_panel_ai_pf button:hover {{
                background: rgba(239,83,80,0.18);
                border-color: #ef5350;
                color: #ffffff;
            }}

            /* Di HP (layar sempit), panel jadi overlay penuh layar biar
               tetap enak dipakai — bukan kolom sempit 380px yang kegencet. */
            @media (max-width: 768px) {{
                .st-key-panel_asisten_ai {{
                    width: 100vw !important;
                    border-left: none;
                }}

                /* Override aturan global "horizontal scroll di layar sempit"
                   (dipasang buat tabel/kartu lebar di halaman utama) — di
                   dalam panel AI ini bikin tombol chip saran kepotong di
                   pinggir layar. Di sini kolomnya dipaksa WRAP ke bawah
                   (bukan discroll ke samping), biar semua tombol kebaca utuh. */
                .st-key-panel_asisten_ai [data-testid="stHorizontalBlock"] {{
                    flex-wrap: wrap !important;
                    overflow-x: visible !important;
                }}
                .st-key-panel_asisten_ai [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
                .st-key-panel_asisten_ai [data-testid="stHorizontalBlock"] > [data-testid="column"] {{
                    flex: 1 1 100% !important;
                    width: 100% !important;
                    min-width: 0 !important;
                }}
            }}
            </style>
            """,
            unsafe_allow_html=True,
        )

        col_judul_ai_pf, col_tutup_ai_pf = st.columns([6, 1])
        with col_judul_ai_pf:
            st.markdown('<div class="gemini-judul">Asisten AI</div>', unsafe_allow_html=True)
        with col_tutup_ai_pf:
            with st.container(key="btn_tutup_panel_ai_pf"):
                if st.button("✕", key="tombol_tutup_panel_ai_pf", help="Tutup panel Asisten AI"):
                    st.session_state["toggle_panel_ai_pf"] = False
                    st.session_state["tampilkan_panel_ai"] = False
                    st.rerun()

        st.markdown(
            """
            <div class="gemini-caption">
                Tanya soal komposisi, diversifikasi, atau performa portofolio kamu. Ini bukan nasihat
                keuangan resmi; AI dapat membuat kesalahan — selalu riset sendiri sebelum mengambil
                keputusan investasi.
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.session_state.riwayat_chat_portofolio and st.button("Bersihkan obrolan", key="btn_bersih_chat_pf", use_container_width=True):
            st.session_state.riwayat_chat_portofolio = []
            simpan_memori_ai_pf([], st.session_state.get("catatan_preferensi_ai_pf", ""))
            st.rerun()

        with st.expander("Preferensi & Data Tambahan"):
            st.caption(
                "Tulis gaya analisis yang kamu suka (mis. 'fokus ke diversifikasi', 'jelasin singkat pakai bullet'). "
                "Ini tersimpan permanen dan otomatis dipakai AI di setiap obrolan berikutnya."
            )
            catatan_baru_pf = st.text_area(
                "Catatan preferensi",
                value=st.session_state.get("catatan_preferensi_ai_pf", ""),
                key="input_catatan_preferensi_pf",
                height=100,
            )
            if st.button("Simpan preferensi", key="btn_simpan_preferensi_pf", use_container_width=True):
                st.session_state.catatan_preferensi_ai_pf = catatan_baru_pf
                simpan_memori_ai_pf(st.session_state.riwayat_chat_portofolio, catatan_baru_pf)
                st.success("Preferensi disimpan.")

            st.markdown("---")
            st.caption("Upload dokumen (txt/csv) buat jadi konteks tambahan AI selama sesi ini berlangsung (tidak disimpan permanen).")
            file_upload_pf = st.file_uploader("Upload file", type=["txt", "csv"], key="upload_dokumen_ai_pf", label_visibility="collapsed")
            if file_upload_pf is not None:
                try:
                    isi_file_pf = file_upload_pf.read().decode("utf-8", errors="ignore")
                    st.session_state.dokumen_diupload_ai_pf = isi_file_pf
                    st.caption(f"{len(isi_file_pf):,} karakter dari '{file_upload_pf.name}' siap dipakai sebagai konteks.")
                except Exception:
                    st.caption("Gagal membaca file. Pastikan formatnya teks biasa (txt/csv).")

        kotak_chat_pf = st.container()
        with kotak_chat_pf:
            if not st.session_state.riwayat_chat_portofolio:
                st.markdown(
                    '<div class="gemini-greeting">Halo! Ada yang bisa saya bantu?</div>',
                    unsafe_allow_html=True,
                )
            else:
                for pesan in st.session_state.riwayat_chat_portofolio:
                    with st.chat_message(pesan["role"]):
                        st.markdown(_escape_dolar(pesan["content"]))

        if not st.session_state.riwayat_chat_portofolio:
            st.markdown('<div class="gemini-chip-label">Coba tanyakan</div>', unsafe_allow_html=True)
            baris1_pf = st.columns(2)
            baris2_pf = st.columns(2)
            kolom_chip_pf = baris1_pf + baris2_pf
            for (ikon, teks), kol in zip(SARAN_PROMPT_AI_PF, kolom_chip_pf):
                with kol:
                    if st.button(f"{ikon}  {teks}", key=f"chip_pf_{teks}", use_container_width=True):
                        konteks_pf = bangun_konteks_portofolio(
                            baris_tampil, total_modal, total_nilai_sekarang, saldo_tersedia, total_equity,
                        )
                        _proses_prompt_ai_pf(kotak_chat_pf, teks, konteks_pf)
                        st.rerun()

        prompt_portofolio = st.chat_input("Contoh: Portofolio saya terlalu terkonsentrasi tidak?", key="chat_input_portofolio")
        if prompt_portofolio:
            konteks_pf = bangun_konteks_portofolio(
                baris_tampil, total_modal, total_nilai_sekarang, saldo_tersedia, total_equity,
            )
            _proses_prompt_ai_pf(kotak_chat_pf, prompt_portofolio, konteks_pf)
            st.rerun()