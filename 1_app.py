import os
from pathlib import Path
import json
import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
import plotly.express as px
from datetime import datetime

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

try:
    from streamlit_autorefresh import st_autorefresh
    AUTOREFRESH_TERSEDIA = True
except ImportError:
    AUTOREFRESH_TERSEDIA = False


@st.cache_resource(show_spinner=False)
def dapatkan_sesi_yf():
    """Session yang 'menyamar' sebagai browser Chrome asli — Yahoo Finance
    sering memblokir/mengembalikan data kosong untuk request polos dari
    server cloud (mis. Streamlit Cloud), session ini mengurangi
    kemungkinan itu terjadi. Dipakai di semua pemanggilan yfinance."""
    if not CURL_CFFI_TERSEDIA:
        return None
    try:
        return curl_requests.Session(impersonate="chrome")
    except Exception:
        return None


# ============================================================
# 0a. Direktori dasar — script INI adalah file utama (root project),
#    jadi cukup pakai folder-nya sendiri (bukan naik satu level kayak
#    file di dalam pages/). daftar_saham_idx.csv & file-file lain yang
#    auto-generate (daftar_tersimpan_idx.json, memori_ai_saham.json)
#    semuanya ditaruh sejajar file ini juga.
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
BASE_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# 0b. Penyimpanan daftar saham yang dibandingkan — KHUSUS halaman ini
#    (page 1 / IDX + global via yfinance). Disimpan ke file JSON terpisah
#    dari page lain (mis. page saham AS & crypto via Finnhub) supaya
#    daftarnya gak kecampur — masing-masing "pages" punya file
#    penyimpanannya sendiri berdasarkan nama filenya sendiri, tapi semua
#    disimpan di folder utama yang sama (BASE_DIR) biar konsisten.
# ============================================================
PATH_DAFTAR_TERSIMPAN = BASE_DIR / "daftar_tersimpan_idx.json"
DAFTAR_SAHAM_DEFAULT = ["BBCA.JK", "BBRI.JK"]


def muat_daftar_tersimpan() -> list:
    if os.path.exists(PATH_DAFTAR_TERSIMPAN):
        try:
            with open(PATH_DAFTAR_TERSIMPAN, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and data:
                    return data
        except Exception:
            pass
    return list(DAFTAR_SAHAM_DEFAULT)


def simpan_daftar_tersimpan(daftar: list):
    try:
        with open(PATH_DAFTAR_TERSIMPAN, "w", encoding="utf-8") as f:
            json.dump(daftar, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # gagal simpan bukan hal fatal, daftar tetap jalan normal di sesi ini


# ============================================================
# 1. Konfigurasi Tampilan Halaman
# ============================================================
st.set_page_config(page_title="Pembanding Saham", layout="wide", page_icon="chart_with_upwards_trend")
st.title("Pembanding Laporan Keuangan Saham")
st.caption("Bandingkan rasio keuangan beberapa emiten sekaligus — cari dari 900+ saham IDX, pilih dari kategori sektor, dan tampilkan grafik per rasio.")

# ============================================================
# 1b. Tampilan & Tema — kustomisasi warna latar website + tema chart TradingView
# ============================================================
TEMA_PRESET = {
    "Gelap Klasik": {"app_bg": "#0e1117", "sidebar_bg": "#131722", "teks": "#e6e6e6"},
    "Midnight Blue": {"app_bg": "#0a0e27", "sidebar_bg": "#10163a", "teks": "#dfe6ff"},
    "Deep Purple": {"app_bg": "#1a1025", "sidebar_bg": "#241536", "teks": "#ecdfff"},
    "Forest Green": {"app_bg": "#0d1f17", "sidebar_bg": "#122b1f", "teks": "#dcf5e6"},
    "Warm Coffee": {"app_bg": "#1f1a17", "sidebar_bg": "#2b241f", "teks": "#f5e9dc"},
    "Terang": {"app_bg": "#ffffff", "sidebar_bg": "#f0f2f6", "teks": "#0e1117"},
}

with st.sidebar.expander("Tampilan & Tema", expanded=False):
    nama_tema = st.selectbox("Tema warna latar website", list(TEMA_PRESET.keys()) + ["Kustom"], key="nama_tema")

    if nama_tema == "Kustom":
        app_bg = st.color_picker("Warna latar utama", "#0e1117", key="custom_app_bg")
        sidebar_bg = st.color_picker("Warna latar sidebar", "#131722", key="custom_sidebar_bg")
        teks_warna = st.color_picker("Warna teks", "#e6e6e6", key="custom_teks")
    else:
        preset = TEMA_PRESET[nama_tema]
        app_bg, sidebar_bg, teks_warna = preset["app_bg"], preset["sidebar_bg"], preset["teks"]

    st.markdown("---")
    tema_chart_tv = st.radio("Tema grafik TradingView", ["dark", "light"], horizontal=True, key="tema_chart_tv")

st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, .stApp, [class*="css"] {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }}

    html {{
        overflow-x: hidden !important;
        max-width: 100vw !important;
        background-color: {app_bg} !important;
        color-scheme: dark;
    }}
    body {{
        overflow-x: hidden !important;
        background-color: {app_bg} !important;
        overscroll-behavior-y: none;
    }}
    .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    [data-testid="stMainBlockContainer"],
    .main,
    section.main {{
        overflow-x: hidden !important;
        max-width: 100vw !important;
        background-color: {app_bg} !important;
    }}

    .stApp {{
        color: {teks_warna};
    }}
    [data-testid="stSidebar"] {{
        background-color: {sidebar_bg} !important;
        border-right: 1px solid rgba(128,128,128,0.12);
    }}
    [data-testid="stSidebar"] * {{
        color: {teks_warna} !important;
    }}
    .stApp, .stApp p, .stApp span, .stApp label {{
        color: {teks_warna};
    }}

    #MainMenu, footer, [data-testid="stDecoration"] {{
        visibility: hidden;
        height: 0;
    }}

    h1 {{ font-weight: 700; letter-spacing: -0.02em; }}
    h2, h3 {{ font-weight: 600; letter-spacing: -0.01em; }}

    .stButton > button, .stDownloadButton > button {{
        background-color: rgba(255,255,255,0.04);
        color: {teks_warna};
        border-radius: 8px;
        border: 1px solid rgba(128,128,128,0.25);
        font-weight: 500;
        transition: all 0.15s ease;
    }}
    .stButton > button:hover, .stDownloadButton > button:hover {{
        border-color: #2962ff;
        color: #2962ff;
    }}
    .stButton > button:disabled {{
        background-color: rgba(255,255,255,0.02);
        color: rgba(255,255,255,0.35) !important;
    }}

    [data-testid="stExpander"] {{
        background-color: rgba(255,255,255,0.02);
        border: 1px solid rgba(128,128,128,0.15);
        border-radius: 10px;
    }}
    [data-testid="stExpander"] summary {{
        background-color: transparent !important;
    }}

    [data-baseweb="tab-list"] {{
        gap: 4px;
    }}
    [data-baseweb="tab"] {{
        border-radius: 8px 8px 0 0;
    }}

    .stTextInput input,
    .stNumberInput input,
    .stDateInput input,
    .stSelectbox > div > div,
    .stMultiSelect > div > div,
    [data-baseweb="select"] > div,
    [data-baseweb="input"] {{
        background-color: rgba(255,255,255,0.04) !important;
        color: {teks_warna} !important;
        border-radius: 8px !important;
        border-color: rgba(128,128,128,0.25) !important;
    }}
    [data-baseweb="tag"] {{
        background-color: rgba(41,98,255,0.25) !important;
    }}

    [data-baseweb="popover"],
    [data-baseweb="menu"],
    ul[role="listbox"],
    li[role="option"] {{
        background-color: {sidebar_bg} !important;
        color: {teks_warna} !important;
    }}
    li[role="option"]:hover {{
        background-color: rgba(255,255,255,0.08) !important;
    }}

    [data-testid="stMetricValue"] {{
        font-weight: 700;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# 2. Muat Daftar Saham Indonesia (dari file CSV bawaan aplikasi)
#    File ini harus berada di folder yang sama dengan script ini.
#    Kategori sektor diklasifikasikan otomatis berdasarkan kata kunci
#    pada nama perusahaan, karena data sumber BEI tidak menyertakan
#    kolom sektor resmi.
# ============================================================
PATH_CSV_SAHAM = BASE_DIR / "daftar_saham_idx.csv"


@st.cache_data(show_spinner=False)
def muat_daftar_saham_idx():
    try:
        df = pd.read_csv(PATH_CSV_SAHAM)
        df["Kode"] = df["Kode"].astype(str).str.strip()
        df["Nama Perusahaan"] = df["Nama Perusahaan"].astype(str).str.strip()
        df["Ticker"] = df["Kode"] + ".JK"
        return df
    except FileNotFoundError:
        return pd.DataFrame(columns=["Kode", "Nama Perusahaan", "Papan Pencatatan", "Kategori", "Ticker"])


df_idx = muat_daftar_saham_idx()

if df_idx.empty:
    st.warning(
        "File `daftar_saham_idx.csv` tidak ditemukan di folder yang sama dengan script ini. "
        "Fitur kategori sektor & pencarian lokal saham Indonesia tidak akan berfungsi penuh — "
        "pastikan file CSV diletakkan satu folder dengan `pembanding_saham_idx.py`."
    )

LABEL_SEMUA_SAHAM = (
    [f"{kode} — {nama}" for kode, nama in zip(df_idx["Ticker"], df_idx["Nama Perusahaan"])]
    if not df_idx.empty else []
)

# Bangun KATEGORI_SAHAM dari CSV: {Sektor: {Ticker: Nama Perusahaan}}
KATEGORI_SAHAM = {}
if not df_idx.empty:
    for kategori, grup in df_idx.groupby("Kategori"):
        KATEGORI_SAHAM[kategori] = dict(zip(grup["Ticker"], grup["Nama Perusahaan"]))

# Tambahkan kategori saham global (di luar CSV BEI) sebagai pelengkap
KATEGORI_SAHAM["Saham AS (Global)"] = {
    "AAPL": "Apple", "MSFT": "Microsoft", "GOOGL": "Alphabet",
    "AMZN": "Amazon", "TSLA": "Tesla", "META": "Meta Platforms", "NVDA": "NVIDIA",
}

# Urutkan kategori: yang jumlah sahamnya lebih banyak & relevan duluan, "Lainnya" & Global di akhir
urutan_prioritas = [k for k in KATEGORI_SAHAM if k not in ("Lainnya", "Saham AS (Global)")]
urutan_prioritas = sorted(urutan_prioritas, key=lambda k: -len(KATEGORI_SAHAM[k]))
urutan_final = urutan_prioritas + [k for k in ("Lainnya", "Saham AS (Global)") if k in KATEGORI_SAHAM]
KATEGORI_SAHAM = {k: KATEGORI_SAHAM[k] for k in urutan_final}


def tebak_simbol_tradingview(ticker: str, exchange_yf: str = None) -> str:
    """Tebakan default simbol TradingView. Saham IDX (.JK) dipetakan ke
    exchange 'IDX:', saham global ditebak dari kode exchange Yahoo Finance
    (info['exchange']) — bukan jaminan selalu tepat, makanya selalu
    disediakan kotak override manual di panel chart."""
    if ticker.upper().endswith(".JK"):
        return f"IDX:{ticker[:-3].upper()}"
    alias_exchange_yf = {
        "NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ",
        "NYQ": "NYSE", "ASE": "AMEX", "PCX": "AMEX",
    }
    exch_tv = alias_exchange_yf.get((exchange_yf or "").upper(), "NASDAQ")
    return f"{exch_tv}:{ticker.upper()}"


# ============================================================
# 3. State: daftar saham yang sedang dibandingkan (dimuat dari file
#    tersimpan khusus halaman ini, biar nyambung terus antar sesi/reload
#    tanpa kecampur sama daftar di halaman lain).
# ============================================================
if "daftar_saham_idx" not in st.session_state:
    st.session_state.daftar_saham_idx = muat_daftar_tersimpan()


def tambah_saham(kode: str):
    kode = kode.strip().upper()
    if kode and kode not in st.session_state.daftar_saham_idx:
        st.session_state.daftar_saham_idx.append(kode)
        simpan_daftar_tersimpan(st.session_state.daftar_saham_idx)


def hapus_saham(kode: str):
    if kode in st.session_state.daftar_saham_idx:
        st.session_state.daftar_saham_idx.remove(kode)
        simpan_daftar_tersimpan(st.session_state.daftar_saham_idx)


# ============================================================
# 4. Fungsi Pencarian Ticker
#    - Pencarian LOKAL: dari 900+ saham Indonesia di CSV (cepat, offline)
#    - Pencarian GLOBAL: via Yahoo Finance, untuk saham luar negeri
# ============================================================
def cari_saham_lokal(kata_kunci: str, maks_hasil: int = 15):
    if df_idx.empty or not kata_kunci or len(kata_kunci.strip()) < 2:
        return pd.DataFrame()
    k = kata_kunci.strip().lower()
    cocok = df_idx[
        df_idx["Kode"].str.lower().str.contains(k, na=False)
        | df_idx["Nama Perusahaan"].str.lower().str.contains(k, na=False)
    ]
    return cocok.head(maks_hasil)


@st.cache_data(ttl=3600, show_spinner=False)
def cari_ticker_global(kata_kunci: str):
    if not kata_kunci or len(kata_kunci.strip()) < 2:
        return []
    try:
        hasil = yf.Search(kata_kunci, max_results=10, session=dapatkan_sesi_yf())
        opsi = []
        for q in hasil.quotes:
            simbol = q.get("symbol", "")
            nama = q.get("shortname") or q.get("longname") or ""
            bursa = q.get("exchange", "")
            if simbol:
                opsi.append(f"{simbol}  —  {nama} ({bursa})")
        return opsi
    except Exception:
        return []


# ============================================================
# 5. Sidebar — Kelola Daftar Saham
# ============================================================
with st.sidebar.expander("Asisten AI", expanded=False):
    if not GEMINI_TERSEDIA:
        st.caption("Fitur ini butuh package `google-generativeai`. Install dengan: `pip install google-generativeai`")
    else:
        st.caption(
            "Masukkan API key Gemini sendiri untuk mengaktifkan asisten AI (ada tier gratis). "
            "API key ini hanya disimpan selama sesi berjalan (tidak ditulis ke file apa pun)."
        )
        st.session_state["gemini_api_key"] = st.text_input(
            "API Key Gemini",
            type="password",
            value=st.session_state.get("gemini_api_key", ""),
            placeholder="AIza...",
            key="input_gemini_api_key",
        )
        st.session_state["model_ai"] = st.text_input(
            "Model",
            value=st.session_state.get("model_ai", "gemini-3.6-flash"),
            key="input_model_ai",
        )
        st.caption("Dapatkan API key gratis di aistudio.google.com/apikey")

if "tampilkan_panel_ai" not in st.session_state:
    st.session_state.tampilkan_panel_ai = False
with st.sidebar.container(border=True):
    st.session_state.tampilkan_panel_ai = st.checkbox(
        "Tampilkan Asisten AI",
        value=st.session_state.tampilkan_panel_ai,
        key="toggle_panel_ai",
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


st.sidebar.header("Kelola Daftar Saham")

with st.sidebar.expander("Pilih dari Kategori Sektor", expanded=True):
    kategori_terpilih = st.selectbox("Kategori", ["Cari Semua Saham"] + list(KATEGORI_SAHAM.keys()))

    if kategori_terpilih == "Cari Semua Saham":
        st.caption(f"Semua {len(df_idx)} saham IDX — ketik di kolom bawah untuk mencari.")
        dipilih = st.multiselect("Pilih saham", LABEL_SEMUA_SAHAM, key="hasil_cari_semua")
    else:
        opsi_kategori = KATEGORI_SAHAM[kategori_terpilih]
        st.caption(f"{len(opsi_kategori)} saham dalam kategori ini.")
        label_opsi = [f"{kode} — {nama}" for kode, nama in opsi_kategori.items()]
        dipilih = st.multiselect(f"Saham di sektor {kategori_terpilih}", label_opsi, key=f"multiselect_{kategori_terpilih}")

    if st.button("Tambahkan yang dipilih", key="btn_tambah_kategori"):
        for item in dipilih:
            tambah_saham(item.split(" — ")[0])
        st.rerun()

with st.sidebar.expander("Cari Saham Luar Negeri (Global)"):
    kueri_global = st.text_input("Nama perusahaan / kode saham asing", placeholder="contoh: apple / AAPL", key="kueri_global")
    if kueri_global:
        hasil_global = cari_ticker_global(kueri_global)
        if hasil_global:
            pilihan_global = st.selectbox("Hasil pencarian", hasil_global, key="pilihan_global")
            if st.button("Tambahkan hasil pencarian", key="btn_tambah_global"):
                tambah_saham(pilihan_global.split("  —  ")[0])
                st.rerun()
        else:
            st.caption("Tidak ada hasil. Coba kata kunci lain.")

with st.sidebar.expander("Tambah Manual (ketik kode ticker)"):
    kode_manual = st.text_input("Kode saham", placeholder="mis. BBCA.JK atau AAPL", key="input_manual")
    if st.button("Tambahkan", key="btn_tambah_manual") and kode_manual:
        tambah_saham(kode_manual)
        st.rerun()

st.sidebar.markdown("### Saham yang Dibandingkan")
st.sidebar.caption("Daftar ini otomatis tersimpan (khusus halaman ini) dan tetap ada walau app di-reload.")
if not st.session_state.daftar_saham_idx:
    st.sidebar.info("Belum ada saham. Tambahkan minimal 2 saham di atas.")
else:
    for kode in st.session_state.daftar_saham_idx:
        c1, c2 = st.sidebar.columns([4, 1])
        c1.write(f"• **{kode}**")
        if c2.button("×", key=f"hapus_{kode}"):
            hapus_saham(kode)
            st.rerun()

    if st.sidebar.button("Clear All", key="btn_clear_all", use_container_width=True):
        st.session_state.daftar_saham_idx = []
        simpan_daftar_tersimpan([])
        st.rerun()

daftar_saham = st.session_state.daftar_saham_idx

# ============================================================
# 6b. Layout dua kolom: halaman utama (kiri) + panel Asisten AI (kanan, persisten)
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

    *, *::before, *::after {{
        box-sizing: border-box;
    }}

    @media (max-width: 768px) {{
        [data-testid="stMainBlockContainer"], .main .block-container {{
            padding-right: 1rem !important;
            padding-left: 1rem !important;
        }}

        [data-testid="stHorizontalBlock"] {{
            flex-wrap: nowrap !important;
            overflow-x: auto !important;
            -webkit-overflow-scrolling: touch;
            scrollbar-width: thin;
        }}
        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
        [data-testid="stHorizontalBlock"] > [data-testid="column"] {{
            flex: 0 0 auto !important;
            width: auto !important;
            min-width: 200px;
        }}

        [data-testid="stDataFrame"],
        [data-testid="stImage"],
        iframe,
        .element-container {{
            max-width: 100% !important;
        }}

        h1 {{ font-size: 1.6rem !important; }}
        h2 {{ font-size: 1.25rem !important; }}
    }}

    .scroll-container, [data-testid="stHorizontalBlock"], [data-testid="stDataFrame"] {{
        -webkit-overflow-scrolling: touch;
        scroll-behavior: smooth;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

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
                    if (cb.innerText && cb.innerText.includes('Tampilkan Asisten AI')) {{
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
    # 6. Fungsi Mengambil & Menghitung Rasio via API Yahoo Finance
    # ============================================================
    def fmt(val, desimal=2):
        try:
            if val is None:
                return None
            return round(float(val), desimal)
        except (TypeError, ValueError):
            return None


    @st.cache_data(ttl=900, show_spinner=False)
    def ambil_rasio_saham(ticker: str):
        try:
            emiten = yf.Ticker(ticker, session=dapatkan_sesi_yf())
            info = emiten.info
            if not info:
                return None

            der_raw = info.get("debtToEquity")
            der = (der_raw / 100) if der_raw else None
            exchange_yf = info.get("exchange", "")

            data = {
                "Nama": info.get("shortName", ticker),
                "Ticker": ticker.upper(),
                "Mata Uang": info.get("currency", ""),
                "Harga": fmt(info.get("currentPrice") or info.get("regularMarketPrice"), 0),
                "Market Cap": info.get("marketCap"),
                "Exchange": exchange_yf,
                "Simbol TradingView": tebak_simbol_tradingview(ticker, exchange_yf),

                "PER (Trailing)": fmt(info.get("trailingPE")),
                "PER (Forward)": fmt(info.get("forwardPE")),
                "PBV": fmt(info.get("priceToBook")),
                "PEG Ratio": fmt(info.get("trailingPegRatio") or info.get("pegRatio")),
                "Price/Sales": fmt(info.get("priceToSalesTrailing12Months")),
                "EV/EBITDA": fmt(info.get("enterpriseToEbitda")),
                "EV/Revenue": fmt(info.get("enterpriseToRevenue")),

                "ROE (%)": fmt((info.get("returnOnEquity") or 0) * 100),
                "ROA (%)": fmt((info.get("returnOnAssets") or 0) * 100),
                "Net Profit Margin (%)": fmt((info.get("profitMargins") or 0) * 100),
                "Gross Margin (%)": fmt((info.get("operatingMargins") or 0) * 100),
                "Operating Margin (%)": fmt((info.get("operatingMargins") or 0) * 100),
                "EPS (Trailing)": fmt(info.get("trailingEps")),
                "EPS (Forward)": fmt(info.get("forwardEps")),

                "Current Ratio": fmt(info.get("currentRatio")),
                "Quick Ratio": fmt(info.get("quickRatio")),
                "DER (Debt to Equity)": fmt(der),
                "Total Debt": info.get("totalDebt"),

                "Revenue Growth (%)": fmt((info.get("revenueGrowth") or 0) * 100),
                "Earnings Growth (%)": fmt((info.get("earningsGrowth") or 0) * 100),
                "Dividend Yield (%)": fmt((info.get("dividendYield") or 0) * 100),
                "Payout Ratio (%)": fmt((info.get("payoutRatio") or 0) * 100),

                "Beta": fmt(info.get("beta")),
                "52W High": fmt(info.get("fiftyTwoWeekHigh"), 0),
                "52W Low": fmt(info.get("fiftyTwoWeekLow"), 0),
            }
            return data
        except Exception:
            return None


    def render_tradingview_widget(simbol_tv: str, tinggi: int = 550, chart_key: str = "tv", tema: str = "dark"):
        """Render TradingView Advanced Real-Time Chart Widget resmi.
        Widget ini narik data historis & real-time-nya sendiri dari
        TradingView — TIDAK memakai data harga dari Yahoo Finance sama
        sekali. Semua kontrol zoom, indikator teknikal, dan timeframe
        sudah bawaan dari widget-nya sendiri."""
        container_id = f"tradingview_{chart_key}"
        html = f"""
        <div class="tradingview-widget-container" style="height:{tinggi}px;">
            <div id="{container_id}" style="height:100%;"></div>
        </div>
        <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
        <script type="text/javascript">
            new TradingView.widget({{
                "autosize": false,
                "width": "100%",
                "height": {tinggi},
                "symbol": "{simbol_tv}",
                "interval": "D",
                "timezone": "Etc/UTC",
                "theme": "{tema}",
                "style": "1",
                "locale": "en",
                "toolbar_bg": "#f1f3f6",
                "enable_publishing": false,
                "allow_symbol_change": true,
                "hide_side_toolbar": false,
                "container_id": "{container_id}"
            }});
        </script>
        """
        components.html(html, height=tinggi + 10, scrolling=False)


    # ============================================================
    # 7. Validasi minimal 1 saham
    # ============================================================
    if len(daftar_saham) < 1:
        st.warning("Tambahkan minimal 1 saham di sidebar untuk mulai melihat datanya.")
        st.stop()

    # ============================================================
    # 8. Ambil data semua saham
    # ============================================================
    with st.spinner(f"Mengambil data untuk {len(daftar_saham)} saham dari Yahoo Finance..."):
        data_semua = {}
        gagal = []
        for kode in daftar_saham:
            d = ambil_rasio_saham(kode)
            if d:
                data_semua[kode] = d
            else:
                gagal.append(kode)

    if gagal:
        st.error(f"Gagal mengambil data untuk: {', '.join(gagal)}. Periksa kembali kode tickernya.")
        if not CURL_CFFI_TERSEDIA:
            st.caption(
                "Catatan: package `curl_cffi` belum terpasang di server ini, jadi request ke Yahoo Finance "
                "lebih mudah diblokir. Install dengan `pip install curl_cffi` lalu restart aplikasinya."
            )
        if st.button("Coba lagi", key="btn_coba_lagi_gagal"):
            ambil_rasio_saham.clear()
            st.rerun()

    if len(data_semua) < 1:
        st.stop()


    def fmt_rp(v):
        return f"{v:,.0f}" if v is not None else "N/A"


    def fmt_cap(v):
        if v is None:
            return "N/A"
        if v >= 1e12:
            return f"{v/1e12:.2f} T"
        if v >= 1e9:
            return f"{v/1e9:.2f} M"
        return f"{v:,.0f}"


    # ============================================================
    # 9. Ringkasan Emiten — kartu bisa discroll ke samping
    # ============================================================
    st.subheader("Ringkasan Emiten")
    st.caption("Geser ke samping ⟶ jika saham yang dibandingkan cukup banyak.")

    st.markdown(
        """
        <style>
        .scroll-container {
            display: flex;
            overflow-x: auto;
            gap: 14px;
            padding: 4px 4px 16px 4px;
        }
        .stock-card {
            flex: 0 0 auto;
            min-width: 230px;
            max-width: 230px;
            background-color: rgba(151, 166, 195, 0.15);
            border: 1px solid rgba(151, 166, 195, 0.35);
            border-radius: 12px;
            padding: 16px;
        }
        .stock-card h4 {
            margin: 0 0 2px 0;
            font-size: 15px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .stock-card .ticker-tag {
            display: inline-block;
            font-size: 11px;
            color: #8a8f99;
            background: rgba(151, 166, 195, 0.2);
            border-radius: 6px;
            padding: 1px 8px;
            margin-bottom: 10px;
        }
        .stock-card .metric-row {
            display: flex;
            justify-content: space-between;
            font-size: 13.5px;
            margin-bottom: 6px;
        }
        .stock-card .metric-label { color: #8a8f99; }
        .stock-card .metric-value { font-weight: 600; }
        .scroll-container::-webkit-scrollbar { height: 8px; }
        .scroll-container::-webkit-scrollbar-thumb {
            background: rgba(151, 166, 195, 0.5);
            border-radius: 4px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


    def buat_kartu_saham(d: dict) -> str:
        per_val = d['PER (Trailing)'] if d['PER (Trailing)'] else 'N/A'
        pbv_val = d['PBV'] if d['PBV'] else 'N/A'
        roe_val = d['ROE (%)'] if d['ROE (%)'] else 'N/A'
        return (
            '<div class="stock-card">'
            f'<h4>{d["Nama"]}</h4>'
            f'<span class="ticker-tag">{d["Ticker"]}</span>'
            '<div class="metric-row">'
            '<span class="metric-label">Harga</span>'
            f'<span class="metric-value">{d["Mata Uang"]} {fmt_rp(d["Harga"])}</span>'
            '</div>'
            '<div class="metric-row">'
            '<span class="metric-label">Market Cap</span>'
            f'<span class="metric-value">{fmt_cap(d["Market Cap"])}</span>'
            '</div>'
            '<div class="metric-row">'
            '<span class="metric-label">PER</span>'
            f'<span class="metric-value">{per_val} x</span>'
            '</div>'
            '<div class="metric-row">'
            '<span class="metric-label">PBV</span>'
            f'<span class="metric-value">{pbv_val} x</span>'
            '</div>'
            '<div class="metric-row">'
            '<span class="metric-label">ROE</span>'
            f'<span class="metric-value">{roe_val} %</span>'
            '</div>'
            '</div>'
        )


    semua_kartu = "".join(buat_kartu_saham(d) for d in data_semua.values())
    kartu_html = f'<div class="scroll-container">{semua_kartu}</div>'
    st.markdown(kartu_html, unsafe_allow_html=True)

    st.markdown("---")

    # ============================================================
    # 9b. Grafik Pergerakan Harga (TradingView Widget)
    # ============================================================
    st.subheader("Pergerakan Harga (TradingView Widget)")
    st.caption(
        "Grafik ini adalah widget resmi TradingView yang narik data historis & real-time-nya "
        "langsung dari TradingView — bukan dari Yahoo Finance. Tebakan simbol TradingView dibuat "
        "otomatis (saham IDX → IDX:KODE, saham global ditebak dari exchange-nya); kalau grafiknya "
        "kosong/salah emiten, edit kotak simbol di bawah chart-nya secara manual."
    )

    if AUTOREFRESH_TERSEDIA:
        st_autorefresh(interval=10 * 60 * 1000, key="autorefresh_harga")
        st.caption("Auto-refresh data ringkasan tiap 10 menit — aktif otomatis.")
    else:
        st.caption("Auto-refresh butuh: `pip install streamlit-autorefresh`")

    if "tickers_chart_terpilih_idx" not in st.session_state:
        st.session_state.tickers_chart_terpilih_idx = [list(data_semua.keys())[0]]

    opsi_chart = list(dict.fromkeys(list(data_semua.keys()) + st.session_state.tickers_chart_terpilih_idx))

    tickers_dipilih = st.multiselect(
        "Pilih saham untuk chart (bisa lebih dari satu untuk bandingin split-screen)",
        options=opsi_chart,
        max_selections=4,
        key="tickers_chart_terpilih_idx",
    )

    col_refresh, _ = st.columns([1, 3])
    with col_refresh:
        if st.button("Refresh Data Ringkasan", key="btn_refresh_manual", use_container_width=True):
            ambil_rasio_saham.clear()
            st.rerun()

    if not tickers_dipilih:
        st.info("Pilih atau cari saham di atas untuk melihat grafik pergerakan harganya.")
    else:
        tinggi_per_chart = 550 if len(tickers_dipilih) == 1 else 420
        for i in range(0, len(tickers_dipilih), 2):
            baris_ticker = tickers_dipilih[i:i + 2]
            kolom = st.columns(len(baris_ticker)) if len(baris_ticker) > 1 else [st.container()]
            for kol, tk in zip(kolom, baris_ticker):
                with kol:
                    d = data_semua.get(tk, {})
                    st.markdown(f"**{d.get('Nama', tk)}** ({tk})")
                    key_override = f"simbol_tv_override_{tk}"
                    default_simbol = d.get("Simbol TradingView", tebak_simbol_tradingview(tk))
                    simbol_tv = st.text_input(
                        "Simbol TradingView", value=default_simbol, key=key_override,
                        help="Format: EXCHANGE:SIMBOL, contoh IDX:BBCA atau NASDAQ:AAPL.",
                    )
                    render_tradingview_widget(
                        simbol_tv, tinggi=tinggi_per_chart,
                        chart_key=f"{tk.replace('.', '_')}", tema=tema_chart_tv,
                    )

        st.caption(
            "Bisa pilih sampai 4 saham sekaligus untuk dibandingkan berdampingan (split-screen). "
            "Semua kontrol zoom, indikator teknikal, dan ganti timeframe ada langsung di dalam widget TradingView-nya."
        )

    st.markdown("---")

    # ============================================================
    # 10. Tabel & Grafik Perbandingan per Kategori Rasio
    # ============================================================
    st.subheader("Perbandingan Rasio Keuangan Lengkap")

    KATEGORI_RASIO = {
        "Valuasi": ["PER (Trailing)", "PER (Forward)", "PBV", "PEG Ratio",
                       "Price/Sales", "EV/EBITDA", "EV/Revenue"],
        "Profitabilitas": ["ROE (%)", "ROA (%)", "Net Profit Margin (%)",
                              "Gross Margin (%)", "Operating Margin (%)",
                              "EPS (Trailing)", "EPS (Forward)"],
        "Likuiditas & Solvabilitas": ["Current Ratio", "Quick Ratio",
                                         "DER (Debt to Equity)"],
        "Pertumbuhan & Dividen": ["Revenue Growth (%)", "Earnings Growth (%)",
                                     "Dividend Yield (%)", "Payout Ratio (%)"],
        "Info Pasar": ["Beta", "52W High", "52W Low"],
    }

    PALET_WARNA = px.colors.qualitative.Set2

    PENJELASAN_INDIKATOR = {
        "PER (Trailing)": "Price to Earnings Ratio berdasarkan laba 12 bulan terakhir. Menunjukkan berapa kali investor membayar harga saham dibanding laba bersih per saham. Semakin rendah, semakin 'murah' saham relatif terhadap labanya — tapi harus dibandingkan dengan saham sejenis.",
        "PER (Forward)": "Sama seperti PER Trailing, tapi memakai estimasi laba 12 bulan ke depan (proyeksi analis), bukan laba historis. Berguna untuk melihat valuasi berdasarkan ekspektasi pertumbuhan ke depan.",
        "PBV": "Price to Book Value — harga saham dibanding nilai buku (aset bersih) per saham. PBV di bawah 1 berarti saham diperdagangkan di bawah nilai aset bersihnya; sering dipakai untuk menilai saham perbankan atau properti.",
        "PEG Ratio": "PER dibagi dengan tingkat pertumbuhan laba. Membantu menilai apakah valuasi (PER) suatu saham sudah wajar dibanding potensi pertumbuhannya. PEG di sekitar 1 sering dianggap wajar.",
        "Price/Sales": "Harga saham dibanding pendapatan (revenue) per saham. Berguna untuk menilai perusahaan yang belum untung tapi pendapatannya besar, karena tidak terpengaruh laba negatif.",
        "EV/EBITDA": "Enterprise Value dibanding EBITDA (laba sebelum bunga, pajak, depresiasi, amortisasi). Mengukur valuasi perusahaan secara menyeluruh termasuk utang, sering dipakai untuk membandingkan perusahaan dengan struktur modal berbeda.",
        "EV/Revenue": "Enterprise Value dibanding total pendapatan. Mirip Price/Sales tapi memperhitungkan utang perusahaan, cocok untuk membandingkan perusahaan padat modal.",
        "ROE (%)": "Return on Equity — seberapa efisien perusahaan menghasilkan laba dari modal pemegang saham. Semakin tinggi ROE, semakin efisien perusahaan memutar ekuitasnya menjadi laba.",
        "ROA (%)": "Return on Assets — seberapa efisien perusahaan menghasilkan laba dari seluruh asetnya (termasuk yang dibiayai utang). Cocok untuk menilai efisiensi operasional secara keseluruhan.",
        "Net Profit Margin (%)": "Persentase laba bersih dari setiap Rupiah pendapatan. Semakin tinggi, semakin besar bagian pendapatan yang benar-benar menjadi keuntungan bersih.",
        "Gross Margin (%)": "Persentase laba kotor (pendapatan dikurangi harga pokok penjualan) dari total pendapatan. Menggambarkan efisiensi produksi/harga jual sebelum biaya operasional lain.",
        "Operating Margin (%)": "Persentase laba operasional (sebelum bunga & pajak) dari pendapatan. Menunjukkan seberapa efisien perusahaan menjalankan bisnis inti sebelum faktor pembiayaan dan pajak.",
        "EPS (Trailing)": "Earning per Share — laba bersih 12 bulan terakhir dibagi jumlah saham beredar. Menunjukkan berapa laba yang menjadi 'jatah' tiap lembar saham.",
        "EPS (Forward)": "Earning per Share berdasarkan estimasi laba 12 bulan ke depan, dipakai untuk menilai potensi pertumbuhan laba per saham ke depannya.",
        "Current Ratio": "Aset lancar dibanding kewajiban lancar. Mengukur kemampuan perusahaan membayar utang jangka pendek dengan aset yang mudah dicairkan. Rasio di atas 1 umumnya dianggap sehat.",
        "Quick Ratio": "Mirip Current Ratio, tapi persediaan (inventory) dikeluarkan dari perhitungan karena dianggap kurang likuid. Mengukur kemampuan bayar utang jangka pendek secara lebih ketat.",
        "DER (Debt to Equity)": "Debt to Equity Ratio — total utang dibanding ekuitas (modal sendiri). Semakin tinggi DER, semakin besar perusahaan dibiayai oleh utang dibanding modal sendiri, yang berarti risiko finansial lebih besar.",
        "Revenue Growth (%)": "Persentase pertumbuhan pendapatan dibanding periode yang sama tahun sebelumnya (year-over-year). Menunjukkan seberapa cepat bisnis perusahaan berkembang dari sisi penjualan.",
        "Earnings Growth (%)": "Persentase pertumbuhan laba bersih dibanding periode yang sama tahun sebelumnya. Berbeda dari revenue growth, ini menunjukkan pertumbuhan dari sisi profitabilitas.",
        "Dividend Yield (%)": "Persentase dividen tahunan dibanding harga saham saat ini. Menunjukkan berapa persen 'imbal hasil kas' yang didapat investor dari dividen, di luar potensi kenaikan harga saham.",
        "Payout Ratio (%)": "Persentase laba bersih yang dibagikan sebagai dividen kepada pemegang saham. Payout ratio tinggi berarti sebagian besar laba dibagikan, bukan ditahan untuk ekspansi.",
        "Beta": "Ukuran volatilitas harga saham dibanding pergerakan pasar secara keseluruhan. Beta > 1 berarti saham cenderung bergerak lebih fluktuatif dari pasar; Beta < 1 berarti lebih stabil.",
        "52W High": "Harga tertinggi saham dalam 52 minggu (1 tahun) terakhir. Sering dipakai sebagai acuan level resistance atau untuk melihat seberapa jauh harga saat ini dari puncaknya.",
        "52W Low": "Harga terendah saham dalam 52 minggu (1 tahun) terakhir. Sering dipakai sebagai acuan level support atau untuk melihat seberapa jauh harga saat ini dari titik terendahnya.",
    }


    def buat_grafik_indikator(nama_indikator: str, df_kat: pd.DataFrame, key_kategori: str):
        """Buat satu grafik bar vertikal untuk satu indikator saja (skala tidak tercampur)."""
        baris = df_kat[df_kat["Indikator"] == nama_indikator]
        if baris.empty:
            return None
        nilai = baris.iloc[0][list(data_semua.keys())]
        chart_df = pd.DataFrame({
            "Saham": nilai.index,
            "Nilai": nilai.values,
        }).dropna(subset=["Nilai"])

        if chart_df.empty:
            return None

        chart_df = chart_df.sort_values("Nilai", ascending=False)

        fig = px.bar(
            chart_df,
            x="Saham",
            y="Nilai",
            color="Saham",
            color_discrete_sequence=PALET_WARNA,
            text="Nilai",
            title=nama_indikator,
        )
        fig.update_traces(
            texttemplate="%{text:.2f}",
            textposition="outside",
            cliponaxis=False,
        )
        fig.update_layout(
            showlegend=False,
            height=380,
            margin=dict(l=10, r=10, t=40, b=10),
            title_font_size=15,
            xaxis_title=None,
            yaxis_title=None,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        return fig


    tabs = st.tabs(list(KATEGORI_RASIO.keys()))

    for tab, (nama_kategori, indikator_list) in zip(tabs, KATEGORI_RASIO.items()):
        with tab:
            df_kat = pd.DataFrame({"Indikator": indikator_list})
            for kode, d in data_semua.items():
                df_kat[kode] = [d.get(ind) for ind in indikator_list]

            df_kat_tampil = df_kat.copy()
            df_kat_tampil["Indikator"] = df_kat_tampil["Indikator"]

            st.caption("Klik salah satu baris indikator untuk melihat penjelasan singkatnya. Klik lagi barisnya untuk menutup.")

            key_select = f"tabel_select_{nama_kategori}"
            event = st.dataframe(
                df_kat_tampil,
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key=key_select,
            )

            baris_terpilih = event.selection.rows if event and event.selection else []
            if baris_terpilih:
                ind_terpilih = indikator_list[baris_terpilih[0]]
                with st.container(border=True):
                    st.markdown(f"**{ind_terpilih}**")
                    st.write(PENJELASAN_INDIKATOR.get(ind_terpilih, "Penjelasan belum tersedia untuk indikator ini."))

            indikator_dipilih = st.multiselect(
                "Pilih rasio yang ingin ditampilkan grafiknya",
                options=indikator_list,
                key=f"pilih_grafik_{nama_kategori}",
                placeholder="Belum ada grafik dipilih — pilih satu atau beberapa rasio di atas",
            )

            if indikator_dipilih:
                grafik_kolom = st.columns(2)
                for i, ind in enumerate(indikator_dipilih):
                    fig = buat_grafik_indikator(ind, df_kat, nama_kategori)
                    target_kolom = grafik_kolom[i % 2]
                    with target_kolom:
                        if fig:
                            st.plotly_chart(fig, use_container_width=True)
                        else:
                            st.caption(f"Data untuk **{ind}** tidak tersedia.")

    st.markdown("---")

    # ============================================================
    # 11. Tabel Ringkasan Gabungan (semua rasio, semua saham)
    # ============================================================
    with st.expander("Lihat semua rasio dalam satu tabel"):
        semua_indikator = [i for sub in KATEGORI_RASIO.values() for i in sub]
        df_semua = pd.DataFrame({"Indikator Finansial": semua_indikator})
        for kode, d in data_semua.items():
            df_semua[kode] = [d.get(ind, "N/A") for ind in semua_indikator]
        st.dataframe(df_semua, use_container_width=True, hide_index=True)

# ============================================================
# 9c. Asisten AI — panel persisten di kolom kanan
# ============================================================
PATH_MEMORI_AI = BASE_DIR / "memori_ai_saham.json"


def muat_memori_ai():
    if os.path.exists(PATH_MEMORI_AI):
        try:
            with open(PATH_MEMORI_AI, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"riwayat": [], "catatan_preferensi": ""}
    return {"riwayat": [], "catatan_preferensi": ""}


def simpan_memori_ai(riwayat: list, catatan_preferensi: str):
    try:
        with open(PATH_MEMORI_AI, "w", encoding="utf-8") as f:
            json.dump({"riwayat": riwayat, "catatan_preferensi": catatan_preferensi}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


SYSTEM_PROMPT_SAHAM = """Kamu adalah asisten analisis saham di dalam sebuah aplikasi pembanding saham. Tugasmu membantu pengguna memahami data rasio keuangan dan harga saham yang sedang mereka bandingkan.

Data saham yang sedang dibandingkan pengguna saat ini:
{konteks}
{blok_preferensi}
{blok_dokumen}
Instruksi:
- Jawab berdasarkan data di atas, jangan mengarang angka yang tidak ada.
- Berikan analisis yang seimbang: sebutkan potensi kelebihan DAN risiko/kekurangan, bukan cuma satu sisi.
- Boleh memberi pandangan soal valuasi (relatif mahal/murah), tren, dan rasio, tapi ini BUKAN rekomendasi beli/jual yang pasti — selalu jelaskan bahwa keputusan akhir ada di tangan pengguna.
- Jangan pernah mengklaim kepastian arah harga di masa depan.
- Kalau ada catatan preferensi pengguna di atas, sesuaikan gaya jawabanmu dengan itu.
- Jawab dalam Bahasa Indonesia, ringkas dan jelas, boleh pakai bullet point kalau perlu.
"""


def bangun_konteks_saham(data_semua: dict) -> str:
    baris = []
    for kode, d in data_semua.items():
        baris.append(
            f"- {d['Nama']} ({kode}): Harga {d['Mata Uang']} {d['Harga']}, "
            f"PER {d['PER (Trailing)']}, PBV {d['PBV']}, ROE {d['ROE (%)']}%, "
            f"DER {d['DER (Debt to Equity)']}, Dividend Yield {d['Dividend Yield (%)']}%, "
            f"Revenue Growth {d['Revenue Growth (%)']}%, EPS {d['EPS (Trailing)']}"
        )
    return "\n".join(baris)


if "riwayat_chat_saham_idx" not in st.session_state:
    memori_awal = muat_memori_ai()
    st.session_state.riwayat_chat_saham_idx = memori_awal["riwayat"]
    st.session_state.catatan_preferensi_ai_idx = memori_awal["catatan_preferensi"]

if "catatan_preferensi_ai_idx" not in st.session_state:
    st.session_state.catatan_preferensi_ai_idx = ""

SARAN_PROMPT_AI = [
    ("📊", "Bandingkan valuasi saham-saham ini"),
    ("⚠️", "Apa risiko utama dari saham ini?"),
    ("💰", "Mana yang dividennya paling menarik?"),
    ("📈", "Bagaimana kesehatan finansialnya?"),
]


def _escape_dolar(teks: str) -> str:
    """Escape tanda '$' supaya Streamlit tidak salah mengira itu sebagai
    pembuka rumus LaTeX (efeknya teks jadi berantakan/pakai font miring
    matematika kalau ada angka rupiah/dolar dalam jawaban AI)."""
    return teks.replace("$", "\\$")


def _proses_prompt_ai(kotak_chat, prompt_teks: str):
    """Kirim satu prompt ke AI, tampilkan langsung di kotak chat, dan simpan ke riwayat (+ memori permanen)."""
    st.session_state.riwayat_chat_saham_idx.append({"role": "user", "content": prompt_teks})
    with kotak_chat:
        with st.chat_message("user"):
            st.markdown(prompt_teks)
        with st.chat_message("assistant"):
            with st.spinner("Menganalisis..."):
                konteks = bangun_konteks_saham(data_semua)

                catatan = st.session_state.get("catatan_preferensi_ai_idx", "").strip()
                blok_preferensi = f"\nCatatan preferensi pengguna (ikuti gaya ini):\n{catatan}\n" if catatan else ""

                dok = st.session_state.get("dokumen_diupload_ai_idx", "").strip()
                blok_dokumen = f"\nData/dokumen tambahan yang diupload pengguna:\n{dok[:6000]}\n" if dok else ""

                jawaban = tanya_ai(
                    SYSTEM_PROMPT_SAHAM.format(
                        konteks=konteks, blok_preferensi=blok_preferensi, blok_dokumen=blok_dokumen,
                    ),
                    st.session_state.riwayat_chat_saham_idx,
                )
            st.markdown(_escape_dolar(jawaban))
    st.session_state.riwayat_chat_saham_idx.append({"role": "assistant", "content": jawaban})
    simpan_memori_ai(st.session_state.riwayat_chat_saham_idx, st.session_state.get("catatan_preferensi_ai_idx", ""))


with st.container(key="panel_asisten_ai"):

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
            @media (max-width: 768px) {{
                .st-key-panel_asisten_ai {{
                    width: 100vw !important;
                    border-left: none;
                }}
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

            .st-key-panel_asisten_ai .st-key-btn_tutup_panel_ai button {{
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
            .st-key-panel_asisten_ai .st-key-btn_tutup_panel_ai button:hover {{
                background: rgba(239,83,80,0.18);
                border-color: #ef5350;
                color: #ffffff;
            }}
            </style>
            """,
            unsafe_allow_html=True,
        )

        col_judul_ai, col_tutup_ai = st.columns([6, 1])
        with col_judul_ai:
            st.markdown('<div class="gemini-judul">Asisten AI</div>', unsafe_allow_html=True)
        with col_tutup_ai:
            with st.container(key="btn_tutup_panel_ai"):
                if st.button("✕", key="tombol_tutup_panel_ai", help="Tutup panel Asisten AI"):
                    st.session_state["toggle_panel_ai"] = False
                    st.session_state["tampilkan_panel_ai"] = False
                    st.rerun()

        st.markdown(
            """
            <div class="gemini-caption">
                Tanya soal saham yang sedang dibandingkan. Ini bukan nasihat keuangan resmi;
                AI dapat membuat kesalahan — selalu riset sendiri sebelum mengambil keputusan investasi.
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.session_state.riwayat_chat_saham_idx and st.button("Bersihkan obrolan", key="btn_bersih_chat_saham_idx", use_container_width=True):
            st.session_state.riwayat_chat_saham_idx = []
            simpan_memori_ai([], st.session_state.get("catatan_preferensi_ai_idx", ""))
            st.rerun()

        with st.expander("Preferensi & Data Tambahan"):
            st.caption(
                "Tulis gaya analisis yang kamu suka (mis. 'fokus ke dividend yield', 'jelasin singkat pakai bullet'). "
                "Ini tersimpan permanen dan otomatis dipakai AI di setiap obrolan berikutnya."
            )
            catatan_baru = st.text_area(
                "Catatan preferensi",
                value=st.session_state.get("catatan_preferensi_ai_idx", ""),
                key="input_catatan_preferensi_idx",
                height=100,
            )
            if st.button("Simpan preferensi", key="btn_simpan_preferensi", use_container_width=True):
                st.session_state.catatan_preferensi_ai_idx = catatan_baru
                simpan_memori_ai(st.session_state.riwayat_chat_saham_idx, catatan_baru)
                st.success("Preferensi disimpan.")

            st.markdown("---")
            st.caption("Upload dokumen (txt/csv) buat jadi konteks tambahan AI selama sesi ini berlangsung (tidak disimpan permanen).")
            file_upload = st.file_uploader("Upload file", type=["txt", "csv"], key="upload_dokumen_ai_idx", label_visibility="collapsed")
            if file_upload is not None:
                try:
                    isi_file = file_upload.read().decode("utf-8", errors="ignore")
                    st.session_state.dokumen_diupload_ai_idx = isi_file
                    st.caption(f"{len(isi_file):,} karakter dari '{file_upload.name}' siap dipakai sebagai konteks.")
                except Exception:
                    st.caption("Gagal membaca file. Pastikan formatnya teks biasa (txt/csv).")

        kotak_chat = st.container()
        with kotak_chat:
            if not st.session_state.riwayat_chat_saham_idx:
                st.markdown(
                    '<div class="gemini-greeting">Halo! Ada yang bisa saya bantu?</div>',
                    unsafe_allow_html=True,
                )
            else:
                for pesan in st.session_state.riwayat_chat_saham_idx:
                    with st.chat_message(pesan["role"]):
                        st.markdown(_escape_dolar(pesan["content"]))

        if not st.session_state.riwayat_chat_saham_idx:
            st.markdown('<div class="gemini-chip-label">Coba tanyakan</div>', unsafe_allow_html=True)
            baris1 = st.columns(2)
            baris2 = st.columns(2)
            kolom_chip = baris1 + baris2
            for (ikon, teks), kol in zip(SARAN_PROMPT_AI, kolom_chip):
                with kol:
                    if st.button(f"{ikon}  {teks}", key=f"chip_{teks}", use_container_width=True):
                        _proses_prompt_ai(kotak_chat, teks)
                        st.rerun()

        prompt_saham = st.chat_input("Tanya soal saham ini...", key="chat_input_saham_idx")
        if prompt_saham:
            _proses_prompt_ai(kotak_chat, prompt_saham)
            st.rerun()