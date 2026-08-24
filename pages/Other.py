import os
import json
import time
import requests
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

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


# ============================================================
# 0. Konstanta & Helper Polygon.io
# ============================================================
POLYGON_BASE_URL = "https://api.polygon.io"


def polygon_api_key() -> str:
    return st.session_state.get("polygon_api_key", "").strip()


def _req_polygon(path: str, params: dict = None, timeout: int = 15):
    """Wrapper request ke Polygon.io. Mengembalikan (json_data, error_msg).
    error_msg None kalau sukses. Menangani kasus umum: key kosong, 401/403
    (key salah/fitur tidak termasuk plan), 429 (rate limit tier gratis:
    5 request/menit)."""
    key = polygon_api_key()
    if not key:
        return None, "API key Polygon belum diisi."

    params = dict(params or {})
    params["apiKey"] = key
    url = f"{POLYGON_BASE_URL}{path}"

    try:
        resp = requests.get(url, params=params, timeout=timeout)
    except requests.exceptions.RequestException as e:
        return None, f"Gagal konek ke Polygon.io: {e}"

    if resp.status_code == 429:
        return None, "Rate limit Polygon.io tercapai (tier gratis = 5 request/menit). Tunggu sebentar lalu coba lagi."
    if resp.status_code in (401, 403):
        return None, "API key Polygon ditolak, atau data ini butuh plan berbayar yang lebih tinggi."
    if resp.status_code == 404:
        return None, "Data tidak ditemukan (ticker mungkin salah/tidak terdaftar di Polygon)."
    if resp.status_code != 200:
        return None, f"Polygon.io mengembalikan status {resp.status_code}."

    try:
        data = resp.json()
    except Exception:
        return None, "Respons Polygon.io tidak bisa dibaca (bukan JSON valid)."

    if data.get("status") in ("ERROR",):
        return None, data.get("error", "Terjadi error dari Polygon.io.")

    return data, None


def is_crypto(ticker: str) -> bool:
    return ticker.upper().startswith("X:")


def label_tampil_ticker(ticker: str) -> str:
    """Untuk crypto, buang prefix 'X:' dan suffix 'USD' biar tampilan lebih ringkas."""
    if is_crypto(ticker):
        inti = ticker.upper().replace("X:", "")
        if inti.endswith("USD"):
            inti = inti[:-3]
        return f"{inti}/USD (Crypto)"
    return ticker.upper()


def normalisasi_kode_crypto(kode: str) -> str:
    """Ubah input user semacam 'BTC' atau 'btc-usd' jadi format Polygon 'X:BTCUSD'."""
    k = kode.strip().upper().replace("-", "").replace("/", "")
    if k.startswith("X:"):
        return k
    if not k.endswith("USD"):
        k = f"{k}USD"
    return f"X:{k}"


# ============================================================
# 1. Konfigurasi Tampilan Halaman
# ============================================================
st.set_page_config(page_title="Pembanding Saham & Crypto", layout="wide", page_icon="chart_with_upwards_trend")
st.title("Pembanding Saham AS & Crypto (via Polygon.io)")
st.caption("Bandingkan rasio keuangan & pergerakan harga saham Amerika Serikat dan crypto sekaligus — data dari Polygon.io.")

# ============================================================
# 1a. API Key Polygon.io
# ============================================================
with st.sidebar.expander("Koneksi Polygon.io", expanded="polygon_api_key" not in st.session_state or not st.session_state.get("polygon_api_key")):
    st.caption(
        "Masukkan API key Polygon.io kamu (ada tier gratis, tapi dibatasi 5 request/menit dan data "
        "end-of-day, bukan real-time). API key ini hanya disimpan selama sesi berjalan (tidak ditulis ke file)."
    )
    st.session_state["polygon_api_key"] = st.text_input(
        "API Key Polygon.io",
        type="password",
        value=st.session_state.get("polygon_api_key", ""),
        placeholder="isi API key kamu di sini",
        key="input_polygon_api_key",
    )
    st.caption("Daftar API key gratis di polygon.io/dashboard/signup")

if not polygon_api_key():
    st.warning("Isi dulu API key Polygon.io di sidebar (bagian 'Koneksi Polygon.io') untuk mulai memakai aplikasi ini.")
    st.stop()


# ============================================================
# 1b. Tampilan & Tema — kustomisasi warna latar website + warna candlestick
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
    st.caption("Warna candlestick di chart pergerakan harga:")
    warna_candle_naik = st.color_picker("Candle Naik", "#26a69a", key="warna_candle_naik")
    warna_candle_turun = st.color_picker("Candle Turun", "#ef5350", key="warna_candle_turun")
    warna_bg_chart = st.color_picker("Latar belakang chart", "#131722", key="warna_bg_chart")

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
# 2. Daftar Kategori Saham AS & Crypto (hardcoded, karena tidak ada
#    CSV BEI di sini — Polygon dipakai untuk pasar global/AS & crypto).
#    Pencarian tambahan (di luar daftar ini) dilakukan live via
#    endpoint /v3/reference/tickers Polygon.
# ============================================================
KATEGORI_SAHAM_AS = {
    "Teknologi": {
        "AAPL": "Apple Inc.", "MSFT": "Microsoft", "GOOGL": "Alphabet (Class A)",
        "AMZN": "Amazon", "META": "Meta Platforms", "NVDA": "NVIDIA", "TSLA": "Tesla",
        "AVGO": "Broadcom", "ORCL": "Oracle", "CRM": "Salesforce", "ADBE": "Adobe",
        "AMD": "Advanced Micro Devices", "INTC": "Intel", "CSCO": "Cisco", "IBM": "IBM",
    },
    "Keuangan": {
        "JPM": "JPMorgan Chase", "BAC": "Bank of America", "WFC": "Wells Fargo",
        "GS": "Goldman Sachs", "MS": "Morgan Stanley", "V": "Visa", "MA": "Mastercard",
        "AXP": "American Express", "C": "Citigroup", "BLK": "BlackRock",
    },
    "Kesehatan": {
        "JNJ": "Johnson & Johnson", "UNH": "UnitedHealth Group", "PFE": "Pfizer",
        "ABBV": "AbbVie", "MRK": "Merck", "LLY": "Eli Lilly", "TMO": "Thermo Fisher",
        "ABT": "Abbott Laboratories",
    },
    "Konsumer": {
        "WMT": "Walmart", "PG": "Procter & Gamble", "KO": "Coca-Cola", "PEP": "PepsiCo",
        "COST": "Costco", "NKE": "Nike", "MCD": "McDonald's", "SBUX": "Starbucks",
        "HD": "Home Depot", "DIS": "Walt Disney",
    },
    "Energi": {
        "XOM": "ExxonMobil", "CVX": "Chevron", "COP": "ConocoPhillips", "SLB": "Schlumberger",
    },
    "Industri": {
        "BA": "Boeing", "CAT": "Caterpillar", "GE": "General Electric", "HON": "Honeywell",
        "UPS": "United Parcel Service",
    },
}

KATEGORI_CRYPTO_RAW = {
    "BTC": "Bitcoin", "ETH": "Ethereum", "SOL": "Solana", "XRP": "XRP",
    "ADA": "Cardano", "DOGE": "Dogecoin", "MATIC": "Polygon", "DOT": "Polkadot",
    "LTC": "Litecoin", "AVAX": "Avalanche",
}
KATEGORI_CRYPTO = {normalisasi_kode_crypto(k): v for k, v in KATEGORI_CRYPTO_RAW.items()}

KATEGORI_SAHAM = dict(KATEGORI_SAHAM_AS)
KATEGORI_SAHAM["Crypto"] = KATEGORI_CRYPTO


# ============================================================
# 3. State: daftar saham/crypto yang sedang dibandingkan
# ============================================================
if "daftar_saham" not in st.session_state:
    st.session_state.daftar_saham = ["AAPL", "MSFT", normalisasi_kode_crypto("BTC")]


def tambah_saham(kode: str):
    kode = kode.strip().upper()
    if kode and kode not in st.session_state.daftar_saham:
        st.session_state.daftar_saham.append(kode)


def hapus_saham(kode: str):
    if kode in st.session_state.daftar_saham:
        st.session_state.daftar_saham.remove(kode)


# ============================================================
# 4. Pencarian Ticker via Polygon.io (saham & crypto)
# ============================================================
@st.cache_data(ttl=3600, show_spinner=False)
def cari_ticker_polygon(kata_kunci: str, market: str):
    """market: 'stocks' atau 'crypto'."""
    if not kata_kunci or len(kata_kunci.strip()) < 2:
        return [], None
    data, err = _req_polygon(
        "/v3/reference/tickers",
        {"search": kata_kunci.strip(), "market": market, "active": "true", "limit": 10},
    )
    if err:
        return [], err
    hasil = []
    for r in data.get("results", []):
        simbol = r.get("ticker", "")
        nama = r.get("name", "")
        bursa = r.get("primary_exchange", "")
        if simbol:
            hasil.append((simbol, nama, bursa))
    return hasil, None


# ============================================================
# 5. Sidebar — Kelola Daftar Saham/Crypto
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


st.sidebar.header("Kelola Daftar Saham & Crypto")

with st.sidebar.expander("Pilih dari Kategori", expanded=True):
    kategori_terpilih = st.selectbox("Kategori", list(KATEGORI_SAHAM.keys()))
    opsi_kategori = KATEGORI_SAHAM[kategori_terpilih]
    st.caption(f"{len(opsi_kategori)} {'coin' if kategori_terpilih == 'Crypto' else 'saham'} dalam kategori ini.")
    label_opsi = [f"{kode} — {nama}" for kode, nama in opsi_kategori.items()]
    dipilih = st.multiselect(f"Pilih dari {kategori_terpilih}", label_opsi, key=f"multiselect_{kategori_terpilih}")

    if st.button("Tambahkan yang dipilih", key="btn_tambah_kategori"):
        for item in dipilih:
            tambah_saham(item.split(" — ")[0])
        st.rerun()

with st.sidebar.expander("Cari Saham AS Lainnya"):
    kueri_saham = st.text_input("Nama perusahaan / kode ticker", placeholder="contoh: netflix / NFLX", key="kueri_saham_polygon")
    if kueri_saham:
        hasil_saham, err_saham = cari_ticker_polygon(kueri_saham, "stocks")
        if err_saham:
            st.caption(f"Gagal mencari: {err_saham}")
        elif hasil_saham:
            label_hasil = [f"{s}  —  {n} ({b})" for s, n, b in hasil_saham]
            pilihan_saham = st.selectbox("Hasil pencarian", label_hasil, key="pilihan_saham_polygon")
            if st.button("Tambahkan hasil pencarian", key="btn_tambah_saham_polygon"):
                tambah_saham(pilihan_saham.split("  —  ")[0])
                st.rerun()
        else:
            st.caption("Tidak ada hasil. Coba kata kunci lain.")

with st.sidebar.expander("Cari Crypto Lainnya"):
    kueri_crypto = st.text_input("Nama / kode coin", placeholder="contoh: shiba inu / SHIB", key="kueri_crypto_polygon")
    if kueri_crypto:
        hasil_crypto, err_crypto = cari_ticker_polygon(kueri_crypto, "crypto")
        if err_crypto:
            st.caption(f"Gagal mencari: {err_crypto}")
        elif hasil_crypto:
            label_hasil_c = [f"{s}  —  {n}" for s, n, _ in hasil_crypto]
            pilihan_crypto = st.selectbox("Hasil pencarian", label_hasil_c, key="pilihan_crypto_polygon")
            if st.button("Tambahkan hasil pencarian", key="btn_tambah_crypto_polygon"):
                tambah_saham(pilihan_crypto.split("  —  ")[0])
                st.rerun()
        else:
            st.caption("Tidak ada hasil. Coba kata kunci lain.")

with st.sidebar.expander("Tambah Manual (ketik kode ticker)"):
    tipe_manual = st.radio("Tipe", ["Saham", "Crypto"], horizontal=True, key="tipe_manual")
    kode_manual = st.text_input(
        "Kode",
        placeholder="mis. NFLX" if tipe_manual == "Saham" else "mis. BTC",
        key="input_manual",
    )
    if st.button("Tambahkan", key="btn_tambah_manual") and kode_manual:
        kode_final = kode_manual.strip().upper() if tipe_manual == "Saham" else normalisasi_kode_crypto(kode_manual)
        tambah_saham(kode_final)
        st.rerun()

st.sidebar.markdown("### Saham & Crypto yang Dibandingkan")
if not st.session_state.daftar_saham:
    st.sidebar.info("Belum ada saham/crypto. Tambahkan minimal 1 di atas.")
else:
    for kode in st.session_state.daftar_saham:
        c1, c2 = st.sidebar.columns([4, 1])
        c1.write(f"• **{label_tampil_ticker(kode)}**")
        if c2.button("×", key=f"hapus_{kode}"):
            hapus_saham(kode)
            st.rerun()

    if st.sidebar.button("Clear All", key="btn_clear_all", use_container_width=True):
        st.session_state.daftar_saham = []
        st.rerun()

daftar_saham = st.session_state.daftar_saham

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
    # 6. Fungsi Mengambil & Menghitung Rasio via Polygon.io
    # ============================================================
    def fmt(val, desimal=2):
        try:
            if val is None:
                return None
            return round(float(val), desimal)
        except (TypeError, ValueError):
            return None


    def _cari_nilai(items: list, *nama_field: str):
        """Cari nilai 'value' dari list item financial statement Polygon
        berdasarkan salah satu nama field yang cocok (case-insensitive)."""
        if not items:
            return None
        for key, item in items.items() if isinstance(items, dict) else []:
            pass
        # struktur Polygon: {"revenues": {"value": ..., "label": ...}, ...}
        if isinstance(items, dict):
            for nf in nama_field:
                if nf in items and isinstance(items[nf], dict):
                    return items[nf].get("value")
        return None


    @st.cache_data(ttl=900, show_spinner=False)
    def ambil_snapshot_harga(ticker: str):
        """Ambil harga terkini (atau close hari sebelumnya kalau snapshot
        tidak tersedia di plan). Berlaku untuk saham & crypto."""
        if is_crypto(ticker):
            data, err = _req_polygon(f"/v2/snapshot/locale/global/markets/crypto/tickers/{ticker}")
            if not err and data and data.get("ticker"):
                t = data["ticker"]
                harga = (t.get("lastTrade") or {}).get("p") or (t.get("day") or {}).get("c")
                harga_kemarin = (t.get("prevDay") or {}).get("c")
                if harga is not None:
                    return {"harga": harga, "harga_kemarin": harga_kemarin}
            # fallback: aggregates 2 hari terakhir
            return _fallback_harga_dari_aggregates(ticker)
        else:
            data, err = _req_polygon(f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}")
            if not err and data and data.get("ticker"):
                t = data["ticker"]
                harga = (t.get("lastTrade") or {}).get("p") or (t.get("day") or {}).get("c")
                harga_kemarin = (t.get("prevDay") or {}).get("c")
                if harga is not None:
                    return {"harga": harga, "harga_kemarin": harga_kemarin}
            return _fallback_harga_dari_aggregates(ticker)


    def _fallback_harga_dari_aggregates(ticker: str):
        """Kalau endpoint snapshot tidak tersedia di plan Polygon, ambil
        2 candle harian terakhir dari endpoint aggregates sebagai gantinya
        (harga close hari terakhir & sebelumnya)."""
        akhir = datetime.utcnow().date()
        mulai = akhir - timedelta(days=10)
        data, err = _req_polygon(
            f"/v2/aggs/ticker/{ticker}/range/1/day/{mulai}/{akhir}",
            {"adjusted": "true", "sort": "desc", "limit": 5},
        )
        if err or not data or not data.get("results"):
            return None
        hasil = data["results"]
        harga = hasil[0]["c"]
        harga_kemarin = hasil[1]["c"] if len(hasil) > 1 else None
        return {"harga": harga, "harga_kemarin": harga_kemarin}


    @st.cache_data(ttl=3600, show_spinner=False)
    def ambil_detail_ticker(ticker: str):
        if is_crypto(ticker):
            return None, None
        data, err = _req_polygon(f"/v3/reference/tickers/{ticker}")
        if err:
            return None, err
        return data.get("results"), None


    @st.cache_data(ttl=3600, show_spinner=False)
    def ambil_financials(ticker: str, limit: int = 2):
        """Ambil laporan keuangan tahunan terakhir (untuk hitung rasio +
        pertumbuhan YoY). Tidak berlaku untuk crypto."""
        if is_crypto(ticker):
            return [], None
        data, err = _req_polygon(
            "/vX/reference/financials",
            {"ticker": ticker, "timeframe": "annual", "limit": limit, "sort": "period_of_report_date"},
        )
        if err:
            return [], err
        hasil = data.get("results", [])
        # urutkan terbaru dulu
        hasil = sorted(hasil, key=lambda r: r.get("end_date", ""), reverse=True)
        return hasil, None


    @st.cache_data(ttl=3600, show_spinner=False)
    def ambil_dividen_12bulan(ticker: str):
        if is_crypto(ticker):
            return 0.0
        data, err = _req_polygon(
            "/v3/reference/dividends",
            {"ticker": ticker, "limit": 8, "order": "desc", "sort": "ex_dividend_date"},
        )
        if err or not data:
            return 0.0
        batas = datetime.utcnow().date() - timedelta(days=370)
        total = 0.0
        for d in data.get("results", []):
            try:
                tgl = datetime.strptime(d.get("ex_dividend_date", ""), "%Y-%m-%d").date()
                if tgl >= batas:
                    total += float(d.get("cash_amount") or 0)
            except Exception:
                continue
        return total


    @st.cache_data(ttl=3600, show_spinner=False)
    def ambil_52w_high_low(ticker: str):
        akhir = datetime.utcnow().date()
        mulai = akhir - timedelta(days=370)
        data, err = _req_polygon(
            f"/v2/aggs/ticker/{ticker}/range/1/day/{mulai}/{akhir}",
            {"adjusted": "true", "sort": "asc", "limit": 400},
        )
        if err or not data or not data.get("results"):
            return None, None
        hasil = data["results"]
        tinggi = max(r["h"] for r in hasil)
        rendah = min(r["l"] for r in hasil)
        return tinggi, rendah


    @st.cache_data(ttl=900, show_spinner=False)
    def ambil_rasio_saham(ticker: str):
        snap = ambil_snapshot_harga(ticker)
        if not snap or snap.get("harga") is None:
            return None

        harga = snap["harga"]
        harga_kemarin = snap.get("harga_kemarin")

        if is_crypto(ticker):
            return {
                "Nama": label_tampil_ticker(ticker),
                "Ticker": ticker,
                "Tipe": "Crypto",
                "Mata Uang": "USD",
                "Harga": harga,
                "Harga Kemarin": harga_kemarin,
                "Market Cap": None,
                # semua rasio fundamental N/A untuk crypto
                "PER (Trailing)": None, "PER (Forward)": None, "PBV": None, "PEG Ratio": None,
                "Price/Sales": None, "EV/EBITDA": None, "EV/Revenue": None,
                "ROE (%)": None, "ROA (%)": None, "Net Profit Margin (%)": None,
                "Gross Margin (%)": None, "Operating Margin (%)": None,
                "EPS (Trailing)": None, "EPS (Forward)": None,
                "Current Ratio": None, "Quick Ratio": None, "DER (Debt to Equity)": None, "Total Debt": None,
                "Revenue Growth (%)": None, "Earnings Growth (%)": None,
                "Dividend Yield (%)": None, "Payout Ratio (%)": None,
                "Beta": None, "52W High": None, "52W Low": None,
            }

        detail, _ = ambil_detail_ticker(ticker)
        fin_list, _ = ambil_financials(ticker, limit=2)
        fin_terbaru = fin_list[0] if fin_list else None
        fin_prev = fin_list[1] if len(fin_list) > 1 else None

        nama = (detail or {}).get("name", ticker)
        mata_uang = (detail or {}).get("currency_name", "usd").upper()
        market_cap = (detail or {}).get("market_cap")
        shares_out = (detail or {}).get("weighted_shares_outstanding") or (detail or {}).get("share_class_shares_outstanding")

        revenue = eps = net_income = gross_profit = operating_income = None
        equity = total_liabilities = total_assets = current_assets = current_liabilities = None
        long_term_debt = short_term_debt = None

        if fin_terbaru:
            fin_data = fin_terbaru.get("financials", {})
            income = fin_data.get("income_statement", {})
            balance = fin_data.get("balance_sheet", {})

            revenue = _cari_nilai(income, "revenues", "total_revenue")
            eps = _cari_nilai(income, "diluted_earnings_per_share", "basic_earnings_per_share")
            net_income = _cari_nilai(income, "net_income_loss")
            gross_profit = _cari_nilai(income, "gross_profit")
            operating_income = _cari_nilai(income, "operating_income_loss")

            equity = _cari_nilai(balance, "equity", "equity_attributable_to_parent")
            total_liabilities = _cari_nilai(balance, "liabilities")
            total_assets = _cari_nilai(balance, "assets")
            current_assets = _cari_nilai(balance, "current_assets")
            current_liabilities = _cari_nilai(balance, "current_liabilities")
            long_term_debt = _cari_nilai(balance, "long_term_debt")
            short_term_debt = _cari_nilai(balance, "short_term_debt", "current_debt")

        revenue_prev = net_income_prev = None
        if fin_prev:
            income_prev = fin_prev.get("financials", {}).get("income_statement", {})
            revenue_prev = _cari_nilai(income_prev, "revenues", "total_revenue")
            net_income_prev = _cari_nilai(income_prev, "net_income_loss")

        per = (harga / eps) if (eps and eps != 0) else None
        book_value_per_share = (equity / shares_out) if (equity and shares_out) else None
        pbv = (harga / book_value_per_share) if book_value_per_share else None
        roe = ((net_income / equity) * 100) if (net_income is not None and equity) else None
        roa = ((net_income / total_assets) * 100) if (net_income is not None and total_assets) else None
        npm = ((net_income / revenue) * 100) if (net_income is not None and revenue) else None
        gpm = ((gross_profit / revenue) * 100) if (gross_profit is not None and revenue) else None
        opm = ((operating_income / revenue) * 100) if (operating_income is not None and revenue) else None
        current_ratio = (current_assets / current_liabilities) if (current_assets and current_liabilities) else None
        der = (total_liabilities / equity) if (total_liabilities is not None and equity) else None
        price_to_sales = (market_cap / revenue) if (market_cap and revenue) else None

        total_debt = None
        if long_term_debt is not None or short_term_debt is not None:
            total_debt = (long_term_debt or 0) + (short_term_debt or 0)

        rev_growth = (((revenue - revenue_prev) / revenue_prev) * 100) if (revenue and revenue_prev) else None
        earn_growth = (((net_income - net_income_prev) / abs(net_income_prev)) * 100) if (net_income is not None and net_income_prev) else None

        dividen_12bulan = ambil_dividen_12bulan(ticker)
        dividend_yield = ((dividen_12bulan / harga) * 100) if (dividen_12bulan and harga) else None
        payout_ratio = ((dividen_12bulan / eps) * 100) if (dividen_12bulan and eps and eps > 0) else None

        tinggi_52w, rendah_52w = ambil_52w_high_low(ticker)

        return {
            "Nama": nama,
            "Ticker": ticker,
            "Tipe": "Saham",
            "Mata Uang": mata_uang,
            "Harga": harga,
            "Harga Kemarin": harga_kemarin,
            "Market Cap": market_cap,

            "PER (Trailing)": fmt(per),
            "PER (Forward)": None,  # tidak tersedia di Polygon reference/financials
            "PBV": fmt(pbv),
            "PEG Ratio": None,  # butuh estimasi pertumbuhan forward, tidak tersedia
            "Price/Sales": fmt(price_to_sales),
            "EV/EBITDA": None,  # butuh EBITDA & enterprise value yang tidak selalu lengkap di plan dasar
            "EV/Revenue": None,

            "ROE (%)": fmt(roe),
            "ROA (%)": fmt(roa),
            "Net Profit Margin (%)": fmt(npm),
            "Gross Margin (%)": fmt(gpm),
            "Operating Margin (%)": fmt(opm),
            "EPS (Trailing)": fmt(eps),
            "EPS (Forward)": None,

            "Current Ratio": fmt(current_ratio),
            "Quick Ratio": None,  # butuh rincian inventory yang tidak selalu tersedia
            "DER (Debt to Equity)": fmt(der),
            "Total Debt": total_debt,

            "Revenue Growth (%)": fmt(rev_growth),
            "Earnings Growth (%)": fmt(earn_growth),
            "Dividend Yield (%)": fmt(dividend_yield),
            "Payout Ratio (%)": fmt(payout_ratio),

            "Beta": None,  # tidak disediakan Polygon reference data
            "52W High": fmt(tinggi_52w, 0),
            "52W Low": fmt(rendah_52w, 0),
        }


    TIMEFRAME_HARGA = {
        "Harian": {"multiplier": 1, "timespan": "day", "rentang_hari": 180},
        "Mingguan": {"multiplier": 1, "timespan": "week", "rentang_hari": 365 * 2},
        "Bulanan": {"multiplier": 1, "timespan": "month", "rentang_hari": 365 * 5},
        "Tahunan": {"multiplier": 1, "timespan": "year", "rentang_hari": 365 * 15},
    }


    @st.cache_data(ttl=600, show_spinner=False)
    def ambil_data_harga(ticker: str, multiplier: int, timespan: str, rentang_hari: int):
        akhir = datetime.utcnow().date()
        mulai = akhir - timedelta(days=rentang_hari)
        data, err = _req_polygon(
            f"/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{mulai}/{akhir}",
            {"adjusted": "true", "sort": "asc", "limit": 5000},
        )
        if err or not data or not data.get("results"):
            return None

        df = pd.DataFrame(data["results"])
        if df.empty:
            return None
        df["Waktu"] = pd.to_datetime(df["t"], unit="ms")
        df = df.rename(columns={"o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume"})
        return df[["Waktu", "Open", "High", "Low", "Close", "Volume"]].dropna()


    def render_tradingview_chart(
        df: pd.DataFrame, ticker: str, tinggi: int = 560, chart_key: str = "tvchart",
        warna_naik: str = "#26a69a", warna_turun: str = "#ef5350", warna_bg_chart: str = "#131722",
    ):
        """Render candlestick + volume pakai library asli TradingView: Lightweight Charts
        (open-source, MIT license, dipakai TradingView sendiri untuk versi gratisnya)."""
        df_js = df.copy()
        df_js["time"] = pd.to_datetime(df_js["Waktu"]).dt.strftime("%Y-%m-%d")
        df_js["PctChange"] = df_js["Close"].pct_change() * 100

        data_candle = df_js[["time", "Open", "High", "Low", "Close", "PctChange"]].rename(
            columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "PctChange": "pctChange"}
        )
        data_candle["pctChange"] = data_candle["pctChange"].where(data_candle["pctChange"].notna(), None)
        data_candle = data_candle.to_dict(orient="records")

        data_volume = [
            {
                "time": row["time"],
                "value": float(row["Volume"]),
                "color": f"{warna_naik}80" if row["Close"] >= row["Open"] else f"{warna_turun}80",
            }
            for row in df_js[["time", "Open", "Close", "Volume"]].to_dict(orient="records")
        ]

        candle_json = json.dumps(data_candle)
        volume_json = json.dumps(data_volume)
        div_id = f"chart_{chart_key}"

        html = f"""
        <div id="{div_id}" style="width:100%; height:{tinggi}px; background:{warna_bg_chart}; border-radius:8px; position:relative;">
            <div id="{div_id}_legend" style="position:absolute; left:12px; top:8px; z-index:5;
                 font-family:-apple-system,Segoe UI,Roboto,sans-serif; font-size:12.5px; color:#d1d4dc;
                 background:rgba(19,23,34,0.72); padding:4px 10px; border-radius:6px; pointer-events:none;
                 white-space:nowrap;"></div>
        </div>
        <script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
        <script>
            (function() {{
                const container = document.getElementById("{div_id}");
                const legendEl = document.getElementById("{div_id}_legend");
                const chart = LightweightCharts.createChart(container, {{
                    width: container.clientWidth,
                    height: {tinggi},
                    layout: {{
                        background: {{ type: "solid", color: "{warna_bg_chart}" }},
                        textColor: "#d1d4dc",
                    }},
                    grid: {{
                        vertLines: {{ color: "#2a2e39" }},
                        horzLines: {{ color: "#2a2e39" }},
                    }},
                    crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
                    rightPriceScale: {{ borderColor: "#2a2e39", scaleMargins: {{ top: 0.1, bottom: 0.25 }} }},
                    timeScale: {{
                        borderColor: "#2a2e39",
                        timeVisible: false,
                        rightOffset: 4,
                        tickMarkFormatter: (time, tickMarkType, locale) => {{
                            const bulanSingkat = ["Jan","Feb","Mar","Apr","Mei","Jun","Jul","Agu","Sep","Okt","Nov","Des"];
                            const d = new Date(time + "T00:00:00Z");
                            switch (tickMarkType) {{
                                case LightweightCharts.TickMarkType.Year:
                                    return d.getUTCFullYear().toString();
                                case LightweightCharts.TickMarkType.Month:
                                    return bulanSingkat[d.getUTCMonth()];
                                case LightweightCharts.TickMarkType.DayOfMonth:
                                    return d.getUTCDate().toString();
                                default:
                                    return d.getUTCFullYear().toString();
                            }}
                        }},
                    }},
                    handleScroll: {{ mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: true }},
                    handleScale: {{ axisPressedMouseMove: true, mouseWheel: true, pinch: true }},
                }});

                const candleData = {candle_json};
                const pctChangeByTime = {{}};
                candleData.forEach(function(bar) {{ pctChangeByTime[bar.time] = bar.pctChange; }});

                const candleSeries = chart.addCandlestickSeries({{
                    upColor: "{warna_naik}", downColor: "{warna_turun}",
                    borderUpColor: "{warna_naik}", borderDownColor: "{warna_turun}",
                    wickUpColor: "{warna_naik}", wickDownColor: "{warna_turun}",
                }});
                candleSeries.setData(candleData);

                const volumeSeries = chart.addHistogramSeries({{
                    priceFormat: {{ type: "volume" }},
                    priceScaleId: "vol",
                }});
                volumeSeries.setData({volume_json});

                chart.priceScale("vol").applyOptions({{
                    scaleMargins: {{ top: 0.82, bottom: 0 }},
                    visible: false,
                }});

                chart.timeScale().fitContent();

                function tampilkanLegend(bar, pct) {{
                    if (!bar) {{ legendEl.innerHTML = ""; return; }}
                    const naik = bar.close >= bar.open;
                    const warna = naik ? "{warna_naik}" : "{warna_turun}";

                    let htmlPersen = "";
                    if (pct !== null && pct !== undefined) {{
                        const naikVsSebelumnya = pct >= 0;
                        const warnaPersen = naikVsSebelumnya ? "{warna_naik}" : "{warna_turun}";
                        const panah = naikVsSebelumnya ? "▲" : "▼";
                        htmlPersen = ' &nbsp; <span style="color:' + warnaPersen + '">' +
                            panah + ' ' + Math.abs(pct).toFixed(2) + '%</span>';
                    }}

                    legendEl.innerHTML =
                        '<b>{ticker}</b>' +
                        ' &nbsp; O <span style="color:' + warna + '">' + bar.open.toFixed(2) + '</span>' +
                        ' &nbsp; H <span style="color:' + warna + '">' + bar.high.toFixed(2) + '</span>' +
                        ' &nbsp; L <span style="color:' + warna + '">' + bar.low.toFixed(2) + '</span>' +
                        ' &nbsp; C <span style="color:' + warna + '">' + bar.close.toFixed(2) + '</span>' +
                        htmlPersen;
                }}
                if (candleData.length > 0) {{
                    const barTerakhir = candleData[candleData.length - 1];
                    tampilkanLegend(barTerakhir, barTerakhir.pctChange);
                }}
                chart.subscribeCrosshairMove(param => {{
                    if (!param || !param.time || !param.seriesData || !param.seriesData.get(candleSeries)) {{
                        if (candleData.length > 0) {{
                            const barTerakhir = candleData[candleData.length - 1];
                            tampilkanLegend(barTerakhir, barTerakhir.pctChange);
                        }}
                        return;
                    }}
                    const barHover = param.seriesData.get(candleSeries);
                    tampilkanLegend(barHover, pctChangeByTime[param.time]);
                }});

                new ResizeObserver(entries => {{
                    if (entries.length === 0 || entries[0].target !== container) return;
                    const newWidth = entries[0].contentRect.width;
                    chart.applyOptions({{ width: newWidth }});
                }}).observe(container);

                const menu = document.createElement("div");
                menu.style.cssText = "position:fixed; display:none; z-index:1000; background:#1e222d; " +
                    "border:1px solid #2a2e39; border-radius:6px; padding:4px 0; " +
                    "font-family:-apple-system,Segoe UI,Roboto,sans-serif; font-size:13px; color:#d1d4dc; " +
                    "box-shadow:0 4px 14px rgba(0,0,0,0.45); min-width:210px;";
                document.body.appendChild(menu);

                function buatItemMenu(labelAwal) {{
                    const item = document.createElement("div");
                    item.textContent = labelAwal;
                    item.style.cssText = "padding:8px 14px; cursor:pointer;";
                    item.onmouseenter = () => item.style.background = "#2a2e39";
                    item.onmouseleave = () => item.style.background = "transparent";
                    menu.appendChild(item);
                    return item;
                }}
                function buatPemisahMenu() {{
                    const pemisah = document.createElement("div");
                    pemisah.style.cssText = "height:1px; background:#2a2e39; margin:4px 0;";
                    menu.appendChild(pemisah);
                }}

                buatItemMenu("Reset Skala Harga").onclick = () => {{
                    chart.priceScale("right").applyOptions({{ autoScale: true }});
                    menu.style.display = "none";
                }};
                buatItemMenu("Reset Skala Waktu").onclick = () => {{
                    chart.timeScale().fitContent();
                    menu.style.display = "none";
                }};
                buatItemMenu("Reset Tampilan (Semua)").onclick = () => {{
                    chart.priceScale("right").applyOptions({{ autoScale: true }});
                    chart.timeScale().fitContent();
                    menu.style.display = "none";
                }};

                buatPemisahMenu();

                let logScaleAktif = false;
                const itemLog = buatItemMenu("Skala Logaritmik: Off");
                itemLog.onclick = () => {{
                    logScaleAktif = !logScaleAktif;
                    chart.priceScale("right").applyOptions({{
                        mode: logScaleAktif ? LightweightCharts.PriceScaleMode.Logarithmic : LightweightCharts.PriceScaleMode.Normal,
                    }});
                    itemLog.textContent = "Skala Logaritmik: " + (logScaleAktif ? "On" : "Off");
                    menu.style.display = "none";
                }};

                buatPemisahMenu();

                buatItemMenu("Unduh sebagai Gambar").onclick = () => {{
                    const canvas = chart.takeScreenshot();
                    const link = document.createElement("a");
                    link.download = "{ticker.replace(':', '_')}_chart.png";
                    link.href = canvas.toDataURL();
                    link.click();
                    menu.style.display = "none";
                }};

                container.addEventListener("contextmenu", (e) => {{
                    e.preventDefault();
                    const batasKanan = window.innerWidth - 220;
                    const batasBawah = window.innerHeight - 220;
                    menu.style.left = Math.min(e.clientX, batasKanan) + "px";
                    menu.style.top = Math.min(e.clientY, batasBawah) + "px";
                    menu.style.display = "block";
                }});
                document.addEventListener("click", () => {{ menu.style.display = "none"; }});
            }})();
        </script>
        """
        components.html(html, height=tinggi + 20, scrolling=False)


    # ============================================================
    # 7. Validasi minimal 1 saham
    # ============================================================
    if len(daftar_saham) < 1:
        st.warning("Tambahkan minimal 1 saham/crypto di sidebar untuk mulai melihat datanya.")
        st.stop()

    # ============================================================
    # 8. Ambil data semua saham/crypto
    #    Catatan: tier gratis Polygon dibatasi 5 request/menit — kalau
    #    daftar bandingannya panjang, ambil datanya bisa butuh waktu
    #    (ada jeda antar-request otomatis di bawah).
    # ============================================================
    with st.spinner(f"Mengambil data untuk {len(daftar_saham)} saham/crypto dari Polygon.io..."):
        data_semua = {}
        gagal = {}
        for i, kode in enumerate(daftar_saham):
            d = ambil_rasio_saham(kode)
            if d:
                data_semua[kode] = d
            else:
                gagal[kode] = "Data tidak tersedia (cek API key/plan, atau kode ticker salah)."
            if i < len(daftar_saham) - 1:
                time.sleep(0.3)  # jeda kecil biar lebih ramah ke rate limit tier gratis

    if gagal:
        st.error("Gagal mengambil data untuk: " + ", ".join(f"{k} ({v})" for k, v in gagal.items()))
        st.caption(
            "Tier gratis Polygon.io dibatasi 5 request/menit dan data end-of-day (bukan real-time). "
            "Kalau baru saja menambahkan banyak ticker sekaligus, coba tunggu ~1 menit lalu klik 'Coba lagi'."
        )
        if st.button("Coba lagi", key="btn_coba_lagi_gagal"):
            ambil_rasio_saham.clear()
            st.rerun()

    if len(data_semua) < 1:
        st.stop()


    def fmt_rp(v):
        return f"{v:,.2f}" if v is not None else "N/A"


    def fmt_cap(v):
        if v is None:
            return "N/A"
        if v >= 1e12:
            return f"{v/1e12:.2f} T"
        if v >= 1e9:
            return f"{v/1e9:.2f} B"
        if v >= 1e6:
            return f"{v/1e6:.2f} M"
        return f"{v:,.0f}"


    # ============================================================
    # 9. Ringkasan Emiten — kartu bisa discroll ke samping
    # ============================================================
    st.subheader("Ringkasan Emiten & Crypto")
    st.caption("Geser ke samping ⟶ jika saham/crypto yang dibandingkan cukup banyak.")

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
        if d["Tipe"] == "Crypto":
            harga_kemarin = d.get("Harga Kemarin")
            persen = None
            if harga_kemarin:
                persen = (d["Harga"] - harga_kemarin) / harga_kemarin * 100
            persen_txt = f"{persen:+.2f}%" if persen is not None else "N/A"
            return (
                '<div class="stock-card">'
                f'<h4>{d["Nama"]}</h4>'
                f'<span class="ticker-tag">{d["Ticker"]}</span>'
                '<div class="metric-row">'
                '<span class="metric-label">Harga</span>'
                f'<span class="metric-value">{d["Mata Uang"]} {fmt_rp(d["Harga"])}</span>'
                '</div>'
                '<div class="metric-row">'
                '<span class="metric-label">Perubahan</span>'
                f'<span class="metric-value">{persen_txt}</span>'
                '</div>'
                '<div class="metric-row">'
                '<span class="metric-label">Rasio Fundamental</span>'
                '<span class="metric-value">N/A (Crypto)</span>'
                '</div>'
                '</div>'
            )
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
    # 9b. Grafik Pergerakan Harga (data Polygon.io)
    # ============================================================
    st.subheader("Pergerakan Harga")
    st.caption(
        "Data harga bersumber dari Polygon.io. Pada tier gratis, data bersifat end-of-day "
        "(bukan streaming real-time)."
    )

    if AUTOREFRESH_TERSEDIA:
        st_autorefresh(interval=10 * 60 * 1000, key="autorefresh_harga")
        st.caption("Auto-refresh tiap 10 menit — aktif otomatis.")
    else:
        st.caption("Auto-refresh butuh: `pip install streamlit-autorefresh`")

    if "tickers_chart_terpilih" not in st.session_state:
        st.session_state.tickers_chart_terpilih = [list(data_semua.keys())[0]]

    opsi_chart = list(dict.fromkeys(list(data_semua.keys()) + st.session_state.tickers_chart_terpilih))

    tickers_dipilih = st.multiselect(
        "Pilih saham/crypto untuk chart (bisa lebih dari satu untuk bandingin split-screen)",
        options=opsi_chart,
        format_func=label_tampil_ticker,
        max_selections=4,
        key="tickers_chart_terpilih",
    )

    col_tf, col_refresh = st.columns([3, 1])
    with col_tf:
        timeframe_terpilih = st.radio(
            "Timeframe candle",
            list(TIMEFRAME_HARGA.keys()),
            horizontal=True,
            key="timeframe_terpilih",
        )
    konfig_tf = TIMEFRAME_HARGA[timeframe_terpilih]
    with col_refresh:
        st.write("")
        st.write("")
        if st.button("Refresh Sekarang", key="btn_refresh_manual", use_container_width=True):
            ambil_data_harga.clear()
            st.rerun()

    LABEL_PERUBAHAN = {
        "Harian": "candle sebelumnya",
        "Mingguan": "candle sebelumnya",
        "Bulanan": "candle sebelumnya",
        "Tahunan": "candle sebelumnya",
    }


    def render_satu_panel_chart(ticker_chart: str, tinggi_chart: int):
        with st.spinner(f"Mengambil data harga {label_tampil_ticker(ticker_chart)}..."):
            data_harga = ambil_data_harga(
                ticker_chart, konfig_tf["multiplier"], konfig_tf["timespan"], konfig_tf["rentang_hari"],
            )

        if data_harga is None or data_harga.empty or len(data_harga) <= 1:
            st.warning(f"Data harga untuk **{label_tampil_ticker(ticker_chart)}** pada timeframe **{timeframe_terpilih}** tidak tersedia.")
            return

        harga_akhir = data_harga["Close"].iloc[-1]
        harga_awal = data_harga["Close"].iloc[-2]
        perubahan = harga_akhir - harga_awal
        persen = (perubahan / harga_awal * 100) if harga_awal else 0

        naik = perubahan >= 0
        warna_perubahan = warna_candle_naik if naik else warna_candle_turun
        tanda = "+" if naik else ""
        nama_perusahaan = data_semua.get(ticker_chart, {}).get("Nama", ticker_chart)
        mata_uang = data_semua.get(ticker_chart, {}).get("Mata Uang", "")

        st.markdown(
            f"""
            <div style="margin-bottom:6px;">
                <div style="font-size:24px; font-weight:700; letter-spacing:-0.01em; line-height:1.2;">
                    {nama_perusahaan}
                    <span style="font-size:15px; font-weight:500; color:#8a8f99;">({label_tampil_ticker(ticker_chart)})</span>
                </div>
                <div style="display:flex; align-items:baseline; gap:12px; margin-top:4px;">
                    <span style="font-size:38px; font-weight:800; letter-spacing:-0.02em;">
                        {mata_uang} {harga_akhir:,.2f}
                    </span>
                    <span style="font-size:17px; font-weight:600; color:{warna_perubahan};">
                        {tanda}{perubahan:,.2f} ({tanda}{persen:.2f}%)
                    </span>
                </div>
                <div style="font-size:12.5px; color:#8a8f99; margin-top:2px;">
                    vs {LABEL_PERUBAHAN[timeframe_terpilih]}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        render_tradingview_chart(
            data_harga, ticker_chart, tinggi=tinggi_chart, chart_key=f"{ticker_chart.replace(':', '_')}_{timeframe_terpilih}",
            warna_naik=warna_candle_naik, warna_turun=warna_candle_turun, warna_bg_chart=warna_bg_chart,
        )


    if not tickers_dipilih:
        st.info("Pilih atau cari saham/crypto di atas untuk melihat grafik pergerakan harganya.")
    else:
        tinggi_per_chart = 550 if len(tickers_dipilih) == 1 else 420
        for i in range(0, len(tickers_dipilih), 2):
            baris_ticker = tickers_dipilih[i:i + 2]
            kolom = st.columns(len(baris_ticker)) if len(baris_ticker) > 1 else [st.container()]
            for kol, tk in zip(kolom, baris_ticker):
                with kol:
                    render_satu_panel_chart(tk, tinggi_per_chart)

        st.caption(
            "**Scroll** = zoom in/out. **Drag di area candle** = geser data. "
            "**Drag di sumbu harga (kanan)** = perbesar/perkecil skala harga. "
            "**Drag di sumbu tanggal (bawah)** = perbesar/perkecil skala waktu. "
            "**Klik kanan di chart** untuk menu reset skala harga/waktu, skala logaritmik, dan unduh gambar chart. "
            "Arahkan kursor ke candle mana pun untuk lihat detail Open/High/Low/Close & persentase perubahannya. "
            "Bisa pilih sampai 4 saham/crypto sekaligus untuk dibandingkan berdampingan (split-screen)."
        )

    st.markdown("---")

    # ============================================================
    # 10. Tabel & Grafik Perbandingan per Kategori Rasio
    # ============================================================
    st.subheader("Perbandingan Rasio Keuangan Lengkap")
    st.caption(
        "Rasio fundamental (PER, PBV, ROE, dsb) hanya berlaku untuk saham — akan tampil kosong untuk crypto. "
        "Beberapa rasio (Beta, PEG Ratio, EV/EBITDA, EV/Revenue, Quick Ratio, PER/EPS Forward) belum tersedia "
        "langsung dari Polygon.io pada plan dasar sehingga tampil N/A."
    )

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
        "PER (Forward)": "Sama seperti PER Trailing, tapi memakai estimasi laba 12 bulan ke depan. Belum tersedia dari Polygon.io pada plan dasar sehingga tampil N/A.",
        "PBV": "Price to Book Value — harga saham dibanding nilai buku (aset bersih) per saham. PBV di bawah 1 berarti saham diperdagangkan di bawah nilai aset bersihnya.",
        "PEG Ratio": "PER dibagi tingkat pertumbuhan laba. Butuh estimasi pertumbuhan forward yang belum tersedia dari Polygon.io pada plan dasar sehingga tampil N/A.",
        "Price/Sales": "Harga saham (via market cap) dibanding total pendapatan. Berguna untuk menilai perusahaan yang belum untung tapi pendapatannya besar.",
        "EV/EBITDA": "Enterprise Value dibanding EBITDA. Belum dihitung otomatis di versi ini karena field EBITDA & enterprise value tidak selalu lengkap tersedia dari Polygon.io.",
        "EV/Revenue": "Enterprise Value dibanding total pendapatan. Sama seperti EV/EBITDA, belum dihitung otomatis di versi ini.",
        "ROE (%)": "Return on Equity — seberapa efisien perusahaan menghasilkan laba dari modal pemegang saham.",
        "ROA (%)": "Return on Assets — seberapa efisien perusahaan menghasilkan laba dari seluruh asetnya.",
        "Net Profit Margin (%)": "Persentase laba bersih dari setiap dolar pendapatan.",
        "Gross Margin (%)": "Persentase laba kotor (pendapatan dikurangi harga pokok penjualan) dari total pendapatan.",
        "Operating Margin (%)": "Persentase laba operasional (sebelum bunga & pajak) dari pendapatan.",
        "EPS (Trailing)": "Earning per Share — laba bersih 12 bulan terakhir dibagi jumlah saham beredar.",
        "EPS (Forward)": "EPS berdasarkan estimasi laba ke depan. Belum tersedia dari Polygon.io pada plan dasar sehingga tampil N/A.",
        "Current Ratio": "Aset lancar dibanding kewajiban lancar. Mengukur kemampuan bayar utang jangka pendek.",
        "Quick Ratio": "Mirip Current Ratio tapi persediaan dikeluarkan. Belum dihitung otomatis karena rincian inventory tidak selalu tersedia dari Polygon.io.",
        "DER (Debt to Equity)": "Total kewajiban dibanding ekuitas. Semakin tinggi, semakin besar perusahaan dibiayai utang dibanding modal sendiri.",
        "Revenue Growth (%)": "Persentase pertumbuhan pendapatan tahunan dibanding tahun sebelumnya (YoY), dihitung dari 2 laporan tahunan terakhir.",
        "Earnings Growth (%)": "Persentase pertumbuhan laba bersih tahunan dibanding tahun sebelumnya (YoY).",
        "Dividend Yield (%)": "Total dividen tunai 12 bulan terakhir dibanding harga saham saat ini.",
        "Payout Ratio (%)": "Perkiraan persentase laba per saham yang dibagikan sebagai dividen tunai 12 bulan terakhir.",
        "Beta": "Ukuran volatilitas saham dibanding pasar. Tidak disediakan langsung oleh Polygon.io reference data sehingga tampil N/A.",
        "52W High": "Harga tertinggi dalam ~52 minggu terakhir, dihitung dari data harian Polygon.io.",
        "52W Low": "Harga terendah dalam ~52 minggu terakhir, dihitung dari data harian Polygon.io.",
    }


    def buat_grafik_indikator(nama_indikator: str, df_kat: pd.DataFrame, key_kategori: str):
        baris = df_kat[df_kat["Indikator"] == nama_indikator]
        if baris.empty:
            return None
        nilai = baris.iloc[0][list(data_semua.keys())]
        chart_df = pd.DataFrame({
            "Saham": [label_tampil_ticker(k) for k in nilai.index],
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
            df_kat_tampil.columns = ["Indikator"] + [label_tampil_ticker(k) for k in data_semua.keys()]

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
    # 11. Tabel Ringkasan Gabungan (semua rasio, semua saham/crypto)
    # ============================================================
    with st.expander("Lihat semua rasio dalam satu tabel"):
        semua_indikator = [i for sub in KATEGORI_RASIO.values() for i in sub]
        df_semua = pd.DataFrame({"Indikator Finansial": semua_indikator})
        for kode, d in data_semua.items():
            df_semua[label_tampil_ticker(kode)] = [d.get(ind, "N/A") if d.get(ind) is not None else "N/A" for ind in semua_indikator]
        st.dataframe(df_semua, use_container_width=True, hide_index=True)

# ============================================================
# 9c. Asisten AI — panel persisten di kolom kanan
# ============================================================
PATH_MEMORI_AI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memori_ai_saham_polygon.json")


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


SYSTEM_PROMPT_SAHAM = """Kamu adalah asisten analisis saham AS & crypto di dalam sebuah aplikasi pembanding. Tugasmu membantu pengguna memahami data rasio keuangan dan harga yang sedang mereka bandingkan.

Data saham/crypto yang sedang dibandingkan pengguna saat ini:
{konteks}
{blok_preferensi}
{blok_dokumen}
Instruksi:
- Jawab berdasarkan data di atas, jangan mengarang angka yang tidak ada. Kalau suatu rasio bernilai N/A (misalnya karena crypto tidak punya laporan keuangan, atau data belum tersedia dari Polygon.io), katakan terus terang bahwa datanya tidak tersedia, jangan menebak.
- Berikan analisis yang seimbang: sebutkan potensi kelebihan DAN risiko/kekurangan, bukan cuma satu sisi.
- Boleh memberi pandangan soal valuasi (relatif mahal/murah), tren, dan rasio, tapi ini BUKAN rekomendasi beli/jual yang pasti — selalu jelaskan bahwa keputusan akhir ada di tangan pengguna.
- Jangan pernah mengklaim kepastian arah harga di masa depan, apalagi untuk crypto yang sangat volatil.
- Kalau ada catatan preferensi pengguna di atas, sesuaikan gaya jawabanmu dengan itu.
- Jawab dalam Bahasa Indonesia, ringkas dan jelas, boleh pakai bullet point kalau perlu.
"""


def bangun_konteks_saham(data_semua: dict) -> str:
    baris = []
    for kode, d in data_semua.items():
        if d["Tipe"] == "Crypto":
            baris.append(f"- {d['Nama']} ({kode}): Harga {d['Mata Uang']} {d['Harga']} (crypto, tidak ada rasio fundamental)")
        else:
            baris.append(
                f"- {d['Nama']} ({kode}): Harga {d['Mata Uang']} {d['Harga']}, "
                f"PER {d['PER (Trailing)']}, PBV {d['PBV']}, ROE {d['ROE (%)']}%, "
                f"DER {d['DER (Debt to Equity)']}, Dividend Yield {d['Dividend Yield (%)']}%, "
                f"Revenue Growth {d['Revenue Growth (%)']}%, EPS {d['EPS (Trailing)']}"
            )
    return "\n".join(baris)


if "riwayat_chat_saham" not in st.session_state:
    memori_awal = muat_memori_ai()
    st.session_state.riwayat_chat_saham = memori_awal["riwayat"]
    st.session_state.catatan_preferensi_ai = memori_awal["catatan_preferensi"]

if "catatan_preferensi_ai" not in st.session_state:
    st.session_state.catatan_preferensi_ai = ""

SARAN_PROMPT_AI = [
    ("📊", "Bandingkan valuasi saham-saham ini"),
    ("⚠️", "Apa risiko utama dari saham/crypto ini?"),
    ("💰", "Mana yang dividennya paling menarik?"),
    ("📈", "Bagaimana kesehatan finansialnya?"),
]


def _escape_dolar(teks: str) -> str:
    return teks.replace("$", "\\$")


def _proses_prompt_ai(kotak_chat, prompt_teks: str):
    st.session_state.riwayat_chat_saham.append({"role": "user", "content": prompt_teks})
    with kotak_chat:
        with st.chat_message("user"):
            st.markdown(prompt_teks)
        with st.chat_message("assistant"):
            with st.spinner("Menganalisis..."):
                konteks = bangun_konteks_saham(data_semua)

                catatan = st.session_state.get("catatan_preferensi_ai", "").strip()
                blok_preferensi = f"\nCatatan preferensi pengguna (ikuti gaya ini):\n{catatan}\n" if catatan else ""

                dok = st.session_state.get("dokumen_diupload_ai", "").strip()
                blok_dokumen = f"\nData/dokumen tambahan yang diupload pengguna:\n{dok[:6000]}\n" if dok else ""

                jawaban = tanya_ai(
                    SYSTEM_PROMPT_SAHAM.format(
                        konteks=konteks, blok_preferensi=blok_preferensi, blok_dokumen=blok_dokumen,
                    ),
                    st.session_state.riwayat_chat_saham,
                )
            st.markdown(_escape_dolar(jawaban))
    st.session_state.riwayat_chat_saham.append({"role": "assistant", "content": jawaban})
    simpan_memori_ai(st.session_state.riwayat_chat_saham, st.session_state.get("catatan_preferensi_ai", ""))


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
                Tanya soal saham/crypto yang sedang dibandingkan. Ini bukan nasihat keuangan resmi;
                AI dapat membuat kesalahan — selalu riset sendiri sebelum mengambil keputusan investasi.
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.session_state.riwayat_chat_saham and st.button("Bersihkan obrolan", key="btn_bersih_chat_saham", use_container_width=True):
            st.session_state.riwayat_chat_saham = []
            simpan_memori_ai([], st.session_state.get("catatan_preferensi_ai", ""))
            st.rerun()

        with st.expander("Preferensi & Data Tambahan"):
            st.caption(
                "Tulis gaya analisis yang kamu suka (mis. 'fokus ke dividend yield', 'jelasin singkat pakai bullet'). "
                "Ini tersimpan permanen dan otomatis dipakai AI di setiap obrolan berikutnya."
            )
            catatan_baru = st.text_area(
                "Catatan preferensi",
                value=st.session_state.get("catatan_preferensi_ai", ""),
                key="input_catatan_preferensi",
                height=100,
            )
            if st.button("Simpan preferensi", key="btn_simpan_preferensi", use_container_width=True):
                st.session_state.catatan_preferensi_ai = catatan_baru
                simpan_memori_ai(st.session_state.riwayat_chat_saham, catatan_baru)
                st.success("Preferensi disimpan.")

            st.markdown("---")
            st.caption("Upload dokumen (txt/csv) buat jadi konteks tambahan AI selama sesi ini berlangsung (tidak disimpan permanen).")
            file_upload = st.file_uploader("Upload file", type=["txt", "csv"], key="upload_dokumen_ai", label_visibility="collapsed")
            if file_upload is not None:
                try:
                    isi_file = file_upload.read().decode("utf-8", errors="ignore")
                    st.session_state.dokumen_diupload_ai = isi_file
                    st.caption(f"{len(isi_file):,} karakter dari '{file_upload.name}' siap dipakai sebagai konteks.")
                except Exception:
                    st.caption("Gagal membaca file. Pastikan formatnya teks biasa (txt/csv).")

        kotak_chat = st.container()
        with kotak_chat:
            if not st.session_state.riwayat_chat_saham:
                st.markdown(
                    '<div class="gemini-greeting">Halo! Ada yang bisa saya bantu?</div>',
                    unsafe_allow_html=True,
                )
            else:
                for pesan in st.session_state.riwayat_chat_saham:
                    with st.chat_message(pesan["role"]):
                        st.markdown(_escape_dolar(pesan["content"]))

        if not st.session_state.riwayat_chat_saham:
            st.markdown('<div class="gemini-chip-label">Coba tanyakan</div>', unsafe_allow_html=True)
            baris1 = st.columns(2)
            baris2 = st.columns(2)
            kolom_chip = baris1 + baris2
            for (ikon, teks), kol in zip(SARAN_PROMPT_AI, kolom_chip):
                with kol:
                    if st.button(f"{ikon}  {teks}", key=f"chip_{teks}", use_container_width=True):
                        _proses_prompt_ai(kotak_chat, teks)
                        st.rerun()

        prompt_saham = st.chat_input("Tanya soal saham/crypto ini...", key="chat_input_saham")
        if prompt_saham:
            _proses_prompt_ai(kotak_chat, prompt_saham)
            st.rerun()