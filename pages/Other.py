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
# 0. Konstanta & Helper Alpaca Market Data API
# ============================================================
# CATATAN PENTING soal Alpaca:
# Alpaca Market Data API cuma nyediain data HARGA (bars, quotes, trades,
# snapshot) — dia TIDAK punya data fundamental/laporan keuangan (PER, PBV,
# ROE, DER, EPS, dividend, revenue growth, market cap, dsb). Jadi semua
# rasio fundamental di app ini tampil "N/A" sebagai placeholder buat nanti
# (misalnya kalau suatu saat mau disambungin ke sumber data fundamental
# terpisah). Yang beneran ditarik dari Alpaca cuma: harga terkini, harga
# penutupan sebelumnya, dan 52-week high/low (semuanya data harga murni).
#
# Base URL Data API: https://data.alpaca.markets
# Base URL Trading API (buat cari daftar ticker/asset): tergantung tipe
# akun (paper/live) — dipilih di sidebar.
DATA_BASE_URL = "https://data.alpaca.markets"
TRADING_BASE_URL_PAPER = "https://paper-api.alpaca.markets"
TRADING_BASE_URL_LIVE = "https://api.alpaca.markets"


def alpaca_headers() -> dict:
    key_id = st.session_state.get("alpaca_key_id", "").strip()
    secret_key = st.session_state.get("alpaca_secret_key", "").strip()
    if not key_id or not secret_key:
        return {}
    return {"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret_key}


def trading_base_url() -> str:
    tipe = st.session_state.get("tipe_akun_alpaca", "Paper (simulasi)")
    return TRADING_BASE_URL_LIVE if tipe == "Live (akun asli)" else TRADING_BASE_URL_PAPER


def _req_alpaca(base_url: str, path: str, params: dict = None, timeout: int = 15):
    """Wrapper request ke Alpaca (Data API atau Trading API tergantung base_url).
    Mengembalikan (json_data, error_msg). error_msg None kalau sukses.
    Menangani kasus umum: key kosong, 401/403 (key salah/plan gak cukup),
    429 (rate limit)."""
    headers = alpaca_headers()
    if not headers:
        return None, "API Key ID / Secret Key Alpaca belum diisi."

    url = f"{base_url}{path}"
    try:
        resp = requests.get(url, headers=headers, params=params or {}, timeout=timeout)
    except requests.exceptions.RequestException as e:
        return None, f"Gagal konek ke Alpaca: {e}"

    if resp.status_code == 429:
        return None, "Rate limit Alpaca tercapai. Tunggu sebentar lalu coba lagi."
    if resp.status_code in (401, 403):
        return None, "API Key Alpaca ditolak, atau data ini butuh subscription/plan yang lebih tinggi."
    if resp.status_code == 404:
        return None, "Data tidak ditemukan (simbol mungkin salah/tidak terdaftar di Alpaca)."
    if resp.status_code != 200:
        return None, f"Alpaca mengembalikan status {resp.status_code}."

    try:
        return resp.json(), None
    except Exception:
        return None, "Respons Alpaca tidak bisa dibaca (bukan JSON valid)."


def _req_alpaca_data(path: str, params: dict = None, timeout: int = 15):
    return _req_alpaca(DATA_BASE_URL, path, params, timeout)


def _req_alpaca_trading(path: str, params: dict = None, timeout: int = 15):
    return _req_alpaca(trading_base_url(), path, params, timeout)


def is_crypto(kode: str) -> bool:
    return "/" in kode


def label_tampil_ticker(kode: str) -> str:
    if is_crypto(kode):
        return f"{kode} (Crypto)"
    return kode.upper()


def normalisasi_kode_crypto(kode: str) -> str:
    """Alpaca pakai format 'BTC/USD' (pakai slash) buat pasangan crypto.
    Ubah input user semacam 'BTC' / 'btc-usd' / 'BTCUSD' jadi 'BTC/USD'."""
    k = kode.strip().upper().replace("-", "").replace(" ", "")
    if "/" in k:
        return k
    if k.endswith("USD"):
        k = k[:-3]
    return f"{k}/USD"


# ============================================================
# 1. Konfigurasi Tampilan Halaman
# ============================================================
st.set_page_config(page_title="Pembanding Saham & Crypto", layout="wide", page_icon="chart_with_upwards_trend")
st.title("Pembanding Saham AS & Crypto (via Alpaca Market Data API)")
st.caption("Bandingkan harga saham Amerika Serikat dan crypto sekaligus — data harga dari Alpaca, grafik dari TradingView Widget.")

st.info(
    "**Catatan:** Alpaca Market Data API cuma nyediain data harga, bukan data fundamental. "
    "Kolom rasio keuangan (PER, PBV, ROE, dividend, dst) di bawah sengaja tampil **N/A** sebagai "
    "placeholder — belum ada sumber datanya di versi ini. Grafik pergerakan harga memakai "
    "**TradingView Widget** resmi (narik data sendiri dari TradingView, jadi bisa saja sedikit "
    "berbeda dengan harga snapshot dari Alpaca di atasnya).",
    icon="ℹ️",
)

# ============================================================
# 1a. API Key Alpaca
# ============================================================
with st.sidebar.expander("Koneksi Alpaca", expanded="alpaca_key_id" not in st.session_state or not st.session_state.get("alpaca_key_id")):
    st.caption(
        "Masukkan API Key ID & Secret Key Alpaca kamu (akun paper trading gratis juga bisa dipakai "
        "buat akses Market Data API). Key ini hanya disimpan selama sesi berjalan (tidak ditulis ke file)."
    )
    st.session_state["alpaca_key_id"] = st.text_input(
        "APCA-API-KEY-ID",
        type="password",
        value=st.session_state.get("alpaca_key_id", ""),
        placeholder="isi API Key ID kamu di sini",
        key="input_alpaca_key_id",
    )
    st.session_state["alpaca_secret_key"] = st.text_input(
        "APCA-API-SECRET-KEY",
        type="password",
        value=st.session_state.get("alpaca_secret_key", ""),
        placeholder="isi API Secret Key kamu di sini",
        key="input_alpaca_secret_key",
    )
    st.session_state["tipe_akun_alpaca"] = st.radio(
        "Tipe akun (buat pencarian daftar ticker via Trading API)",
        ["Paper (simulasi)", "Live (akun asli)"],
        horizontal=True,
        key="input_tipe_akun_alpaca",
    )
    st.caption("Daftar API key gratis di app.alpaca.markets (pilih akun Paper Trading kalau belum mau pakai akun live).")

if not alpaca_headers():
    st.warning("Isi dulu API Key ID & Secret Key Alpaca di sidebar (bagian 'Koneksi Alpaca') untuk mulai memakai aplikasi ini.")
    st.stop()


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
# 2. Daftar Kategori Saham AS & Crypto (hardcoded — dipakai buat quick-pick
#    di sidebar; pencarian tambahan di luar daftar ini dilakukan live via
#    endpoint /v2/assets Alpaca Trading API).
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
    "ADA": "Cardano", "DOGE": "Dogecoin", "DOT": "Polkadot",
    "LTC": "Litecoin", "AVAX": "Avalanche", "LINK": "Chainlink",
}
KATEGORI_CRYPTO = {normalisasi_kode_crypto(k): v for k, v in KATEGORI_CRYPTO_RAW.items()}

KATEGORI_SAHAM = dict(KATEGORI_SAHAM_AS)
KATEGORI_SAHAM["Crypto"] = KATEGORI_CRYPTO

# Alias exchange Alpaca -> kode exchange yang dikenali TradingView.
ALIAS_EXCHANGE_TV = {
    "NASDAQ": "NASDAQ", "NYSE": "NYSE", "NYSEARCA": "AMEX", "ARCA": "AMEX",
    "AMEX": "AMEX", "BATS": "BATS", "OTC": "OTC",
}


def tebak_simbol_tradingview(kode: str, exchange_alpaca: str = None) -> str:
    """Tebakan default simbol TradingView. Bukan jaminan selalu tepat —
    makanya di panel chart selalu disediakan kotak buat override manual."""
    if is_crypto(kode):
        inti = kode.replace("/", "")
        return f"COINBASE:{inti}"
    exch_tv = ALIAS_EXCHANGE_TV.get((exchange_alpaca or "").upper(), "NASDAQ")
    return f"{exch_tv}:{kode.upper()}"


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
# 4. Pencarian Ticker via Alpaca Trading API (/v2/assets)
#    Endpoint ini gak punya parameter "search" — jadi kita ambil daftar
#    lengkapnya sekali (di-cache lumayan lama), lalu difilter di sisi
#    Python berdasarkan kata kunci.
# ============================================================
@st.cache_data(ttl=6 * 3600, show_spinner=False)
def ambil_semua_aset(asset_class: str):
    """asset_class: 'us_equity' atau 'crypto'."""
    data, err = _req_alpaca_trading(
        "/v2/assets", {"status": "active", "asset_class": asset_class}
    )
    if err:
        return [], err
    return data or [], None


def cari_ticker_alpaca(kata_kunci: str, asset_class: str):
    if not kata_kunci or len(kata_kunci.strip()) < 2:
        return [], None
    semua, err = ambil_semua_aset(asset_class)
    if err:
        return [], err
    kk = kata_kunci.strip().upper()
    hasil = []
    for a in semua:
        simbol = a.get("symbol", "")
        nama = a.get("name", "") or ""
        if not a.get("tradable", True):
            continue
        if kk in simbol.upper() or kk in nama.upper():
            hasil.append((simbol, nama, a.get("exchange", "")))
        if len(hasil) >= 15:
            break
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
    kueri_saham = st.text_input("Nama perusahaan / kode ticker", placeholder="contoh: netflix / NFLX", key="kueri_saham_alpaca")
    if kueri_saham:
        hasil_saham, err_saham = cari_ticker_alpaca(kueri_saham, "us_equity")
        if err_saham:
            st.caption(f"Gagal mencari: {err_saham}")
        elif hasil_saham:
            label_hasil = [f"{s}  —  {n} ({b})" for s, n, b in hasil_saham]
            pilihan_saham = st.selectbox("Hasil pencarian", label_hasil, key="pilihan_saham_alpaca")
            if st.button("Tambahkan hasil pencarian", key="btn_tambah_saham_alpaca"):
                tambah_saham(pilihan_saham.split("  —  ")[0])
                st.rerun()
        else:
            st.caption("Tidak ada hasil. Coba kata kunci lain.")

with st.sidebar.expander("Cari Crypto Lainnya"):
    kueri_crypto = st.text_input("Nama / kode coin", placeholder="contoh: shiba inu / SHIB", key="kueri_crypto_alpaca")
    if kueri_crypto:
        hasil_crypto, err_crypto = cari_ticker_alpaca(kueri_crypto, "crypto")
        if err_crypto:
            st.caption(f"Gagal mencari: {err_crypto}")
        elif hasil_crypto:
            label_hasil_c = [f"{s}  —  {n}" for s, n, _ in hasil_crypto]
            pilihan_crypto = st.selectbox("Hasil pencarian", label_hasil_c, key="pilihan_crypto_alpaca")
            if st.button("Tambahkan hasil pencarian", key="btn_tambah_crypto_alpaca"):
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
    # 6. Fungsi Mengambil Data Harga via Alpaca (snapshot + 52w high/low)
    # ============================================================
    def fmt(val, desimal=2):
        try:
            if val is None:
                return None
            return round(float(val), desimal)
        except (TypeError, ValueError):
            return None


    @st.cache_data(ttl=900, show_spinner=False)
    def ambil_snapshot_batch(daftar_stock: tuple, daftar_crypto: tuple):
        """Ambil snapshot (harga terkini + harga kemarin) untuk sekumpulan
        saham & crypto sekaligus (dibatch jadi 1-2 request, bukan per-ticker,
        biar hemat kuota). Return dict {kode: {"harga":..., "harga_kemarin":...}}."""
        hasil = {}

        if daftar_stock:
            data, err = _req_alpaca_data(
                "/v2/stocks/snapshots", {"symbols": ",".join(daftar_stock), "feed": "iex"}
            )
            if not err and data:
                for simbol, snap in (data.get("snapshots") or data).items():
                    if not isinstance(snap, dict):
                        continue
                    harga = None
                    if snap.get("latestTrade"):
                        harga = snap["latestTrade"].get("p")
                    if harga is None and snap.get("dailyBar"):
                        harga = snap["dailyBar"].get("c")
                    harga_kemarin = None
                    if snap.get("prevDailyBar"):
                        harga_kemarin = snap["prevDailyBar"].get("c")
                    if harga is not None:
                        hasil[simbol] = {"harga": harga, "harga_kemarin": harga_kemarin}

        if daftar_crypto:
            data, err = _req_alpaca_data(
                "/v1beta3/crypto/us/snapshots", {"symbols": ",".join(daftar_crypto)}
            )
            if not err and data:
                for simbol, snap in (data.get("snapshots") or {}).items():
                    if not isinstance(snap, dict):
                        continue
                    harga = None
                    if snap.get("latestTrade"):
                        harga = snap["latestTrade"].get("p")
                    if harga is None and snap.get("dailyBar"):
                        harga = snap["dailyBar"].get("c")
                    harga_kemarin = None
                    if snap.get("prevDailyBar"):
                        harga_kemarin = snap["prevDailyBar"].get("c")
                    if harga is not None:
                        hasil[simbol] = {"harga": harga, "harga_kemarin": harga_kemarin}

        return hasil


    @st.cache_data(ttl=3600, show_spinner=False)
    def ambil_52w_high_low_batch(daftar_stock: tuple, daftar_crypto: tuple):
        """Ambil high/low ~52 minggu terakhir dari daily bars (dibatch)."""
        hasil = {}
        akhir = datetime.utcnow().date()
        mulai = akhir - timedelta(days=370)

        if daftar_stock:
            data, err = _req_alpaca_data(
                "/v2/stocks/bars",
                {
                    "symbols": ",".join(daftar_stock),
                    "timeframe": "1Day",
                    "start": mulai.isoformat(),
                    "end": akhir.isoformat(),
                    "limit": 10000,
                    "feed": "iex",
                    "adjustment": "split",
                },
            )
            if not err and data and data.get("bars"):
                for simbol, bars in data["bars"].items():
                    if not bars:
                        continue
                    hasil[simbol] = (max(b["h"] for b in bars), min(b["l"] for b in bars))

        if daftar_crypto:
            data, err = _req_alpaca_data(
                "/v1beta3/crypto/us/bars",
                {
                    "symbols": ",".join(daftar_crypto),
                    "timeframe": "1Day",
                    "start": mulai.isoformat(),
                    "end": akhir.isoformat(),
                    "limit": 10000,
                },
            )
            if not err and data and data.get("bars"):
                for simbol, bars in data["bars"].items():
                    if not bars:
                        continue
                    hasil[simbol] = (max(b["h"] for b in bars), min(b["l"] for b in bars))

        return hasil


    @st.cache_data(ttl=6 * 3600, show_spinner=False)
    def ambil_nama_exchange_saham(simbol: str):
        """Ambil nama perusahaan & exchange dari daftar aset yang sudah di-cache
        (dipakai buat label kartu & tebakan simbol TradingView)."""
        semua, err = ambil_semua_aset("us_equity")
        if err:
            return simbol, None
        for a in semua:
            if a.get("symbol") == simbol:
                return a.get("name", simbol), a.get("exchange")
        return simbol, None


    def bangun_ringkasan(daftar_kode: list) -> dict:
        daftar_stock = tuple(k for k in daftar_kode if not is_crypto(k))
        daftar_crypto = tuple(k for k in daftar_kode if is_crypto(k))

        snapshot = ambil_snapshot_batch(daftar_stock, daftar_crypto)
        hilo = ambil_52w_high_low_batch(daftar_stock, daftar_crypto)

        data_semua = {}
        for kode in daftar_kode:
            snap = snapshot.get(kode)
            if not snap or snap.get("harga") is None:
                continue

            tinggi_52w, rendah_52w = hilo.get(kode, (None, None))

            if is_crypto(kode):
                nama = KATEGORI_CRYPTO.get(kode, kode.replace("/USD", ""))
                exch = None
            else:
                nama, exch = ambil_nama_exchange_saham(kode)

            data_semua[kode] = {
                "Nama": nama,
                "Ticker": kode,
                "Tipe": "Crypto" if is_crypto(kode) else "Saham",
                "Mata Uang": "USD",
                "Harga": snap["harga"],
                "Harga Kemarin": snap.get("harga_kemarin"),
                "Exchange": exch,
                "Simbol TradingView": tebak_simbol_tradingview(kode, exch),

                # --- Rasio fundamental: TIDAK tersedia dari Alpaca Market Data API ---
                "Market Cap": None,
                "PER (Trailing)": None, "PER (Forward)": None, "PBV": None, "PEG Ratio": None,
                "Price/Sales": None, "EV/EBITDA": None, "EV/Revenue": None,
                "ROE (%)": None, "ROA (%)": None, "Net Profit Margin (%)": None,
                "Gross Margin (%)": None, "Operating Margin (%)": None,
                "EPS (Trailing)": None, "EPS (Forward)": None,
                "Current Ratio": None, "Quick Ratio": None, "DER (Debt to Equity)": None, "Total Debt": None,
                "Revenue Growth (%)": None, "Earnings Growth (%)": None,
                "Dividend Yield (%)": None, "Payout Ratio (%)": None,
                "Beta": None,
                "52W High": fmt(tinggi_52w, 0),
                "52W Low": fmt(rendah_52w, 0),
            }
        return data_semua


    def render_tradingview_widget(simbol_tv: str, tinggi: int = 550, chart_key: str = "tv", tema: str = "dark"):
        """Render TradingView Advanced Real-Time Chart Widget resmi.
        Widget ini narik data historis & real-time-nya sendiri dari
        TradingView — TIDAK memakai data OHLC dari Alpaca sama sekali."""
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
        st.warning("Tambahkan minimal 1 saham/crypto di sidebar untuk mulai melihat datanya.")
        st.stop()

    # ============================================================
    # 8. Ambil data semua saham/crypto (dibatch, bukan loop per-ticker)
    # ============================================================
    with st.spinner(f"Mengambil data untuk {len(daftar_saham)} saham/crypto dari Alpaca..."):
        data_semua = bangun_ringkasan(daftar_saham)

    gagal = [k for k in daftar_saham if k not in data_semua]
    if gagal:
        st.error("Gagal mengambil data untuk: " + ", ".join(gagal))
        st.caption(
            "Cek lagi API Key Alpaca kamu, atau pastikan kode ticker/pair-nya benar "
            "(saham AS pakai kode biasa mis. AAPL, crypto pakai format SIMBOL/USD mis. BTC/USD)."
        )
        if st.button("Coba lagi", key="btn_coba_lagi_gagal"):
            ambil_snapshot_batch.clear()
            ambil_52w_high_low_batch.clear()
            st.rerun()

    if len(data_semua) < 1:
        st.stop()


    def fmt_rp(v):
        return f"{v:,.2f}" if v is not None else "N/A"


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
        harga_kemarin = d.get("Harga Kemarin")
        persen = None
        if harga_kemarin:
            persen = (d["Harga"] - harga_kemarin) / harga_kemarin * 100
        persen_txt = f"{persen:+.2f}%" if persen is not None else "N/A"
        h52 = d.get("52W High")
        l52 = d.get("52W Low")
        h52_txt = f"{h52:,.0f}" if h52 is not None else "N/A"
        l52_txt = f"{l52:,.0f}" if l52 is not None else "N/A"
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
            '<span class="metric-label">52W High/Low</span>'
            f'<span class="metric-value">{h52_txt} / {l52_txt}</span>'
            '</div>'
            '<div class="metric-row">'
            '<span class="metric-label">Rasio Fundamental</span>'
            '<span class="metric-value">N/A</span>'
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
        "langsung dari TradingView — bukan dari Alpaca. Tebakan simbol TradingView dibuat "
        "otomatis dari exchange yang tercatat di Alpaca; kalau grafiknya kosong/salah emiten, "
        "edit kotak simbol di bawah chart-nya secara manual."
    )

    if AUTOREFRESH_TERSEDIA:
        st_autorefresh(interval=10 * 60 * 1000, key="autorefresh_harga")
        st.caption("Auto-refresh data ringkasan tiap 10 menit — aktif otomatis.")
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

    col_refresh, _ = st.columns([1, 3])
    with col_refresh:
        if st.button("Refresh Data Ringkasan", key="btn_refresh_manual", use_container_width=True):
            ambil_snapshot_batch.clear()
            ambil_52w_high_low_batch.clear()
            st.rerun()

    if not tickers_dipilih:
        st.info("Pilih atau cari saham/crypto di atas untuk melihat grafik pergerakan harganya.")
    else:
        tinggi_per_chart = 550 if len(tickers_dipilih) == 1 else 420
        for i in range(0, len(tickers_dipilih), 2):
            baris_ticker = tickers_dipilih[i:i + 2]
            kolom = st.columns(len(baris_ticker)) if len(baris_ticker) > 1 else [st.container()]
            for kol, tk in zip(kolom, baris_ticker):
                with kol:
                    d = data_semua.get(tk, {})
                    st.markdown(f"**{d.get('Nama', tk)}** ({label_tampil_ticker(tk)})")
                    key_override = f"simbol_tv_override_{tk}"
                    default_simbol = d.get("Simbol TradingView", tebak_simbol_tradingview(tk))
                    simbol_tv = st.text_input(
                        "Simbol TradingView", value=default_simbol, key=key_override,
                        help="Format: EXCHANGE:SIMBOL, contoh NASDAQ:AAPL atau COINBASE:BTCUSD.",
                    )
                    render_tradingview_widget(
                        simbol_tv, tinggi=tinggi_per_chart,
                        chart_key=f"{tk.replace('/', '_')}", tema=tema_chart_tv,
                    )

        st.caption(
            "Bisa pilih sampai 4 saham/crypto sekaligus untuk dibandingkan berdampingan (split-screen). "
            "Semua kontrol zoom, indikator teknikal, dan ganti timeframe ada langsung di dalam widget TradingView-nya."
        )

    st.markdown("---")

    # ============================================================
    # 10. Tabel & Grafik Perbandingan per Kategori Rasio
    # ============================================================
    st.subheader("Perbandingan Rasio Keuangan")
    st.caption(
        "Alpaca Market Data API tidak menyediakan data fundamental/laporan keuangan, jadi semua "
        "rasio di bawah ini (kecuali 52W High/Low, yang murni data harga) tampil **N/A** sebagai "
        "placeholder untuk pengembangan berikutnya."
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
        "PER (Trailing)": "Price to Earnings Ratio berdasarkan laba 12 bulan terakhir. Belum tersedia — Alpaca Market Data API tidak menyediakan data laporan keuangan.",
        "PER (Forward)": "PER berdasarkan estimasi laba ke depan. Belum tersedia dari Alpaca.",
        "PBV": "Price to Book Value. Belum tersedia — butuh data ekuitas/nilai buku yang tidak disediakan Alpaca.",
        "PEG Ratio": "PER dibagi tingkat pertumbuhan laba. Belum tersedia dari Alpaca.",
        "Price/Sales": "Harga saham dibanding pendapatan. Belum tersedia — butuh data pendapatan perusahaan.",
        "EV/EBITDA": "Enterprise Value dibanding EBITDA. Belum tersedia dari Alpaca.",
        "EV/Revenue": "Enterprise Value dibanding pendapatan. Belum tersedia dari Alpaca.",
        "ROE (%)": "Return on Equity. Belum tersedia — butuh data laba bersih & ekuitas dari laporan keuangan.",
        "ROA (%)": "Return on Assets. Belum tersedia dari Alpaca.",
        "Net Profit Margin (%)": "Persentase laba bersih dari pendapatan. Belum tersedia dari Alpaca.",
        "Gross Margin (%)": "Persentase laba kotor dari pendapatan. Belum tersedia dari Alpaca.",
        "Operating Margin (%)": "Persentase laba operasional dari pendapatan. Belum tersedia dari Alpaca.",
        "EPS (Trailing)": "Laba bersih 12 bulan terakhir per saham. Belum tersedia dari Alpaca.",
        "EPS (Forward)": "EPS berdasarkan estimasi laba ke depan. Belum tersedia dari Alpaca.",
        "Current Ratio": "Aset lancar dibanding kewajiban lancar. Belum tersedia — butuh data neraca keuangan.",
        "Quick Ratio": "Mirip Current Ratio tapi persediaan dikeluarkan. Belum tersedia dari Alpaca.",
        "DER (Debt to Equity)": "Total kewajiban dibanding ekuitas. Belum tersedia dari Alpaca.",
        "Revenue Growth (%)": "Pertumbuhan pendapatan tahunan (YoY). Belum tersedia dari Alpaca.",
        "Earnings Growth (%)": "Pertumbuhan laba bersih tahunan (YoY). Belum tersedia dari Alpaca.",
        "Dividend Yield (%)": "Total dividen tunai 12 bulan terakhir dibanding harga saham. Belum tersedia dari Alpaca.",
        "Payout Ratio (%)": "Persentase laba per saham yang dibagikan sebagai dividen. Belum tersedia dari Alpaca.",
        "Beta": "Ukuran volatilitas saham dibanding pasar. Belum dihitung di versi ini (bisa dihitung manual dari data harga historis vs indeks acuan, tapi belum diimplementasikan).",
        "52W High": "Harga tertinggi dalam ~52 minggu terakhir, dihitung dari data harian Alpaca.",
        "52W Low": "Harga terendah dalam ~52 minggu terakhir, dihitung dari data harian Alpaca.",
    }


    def buat_grafik_indikator(nama_indikator: str, df_kat: pd.DataFrame):
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
                    fig = buat_grafik_indikator(ind, df_kat)
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
PATH_MEMORI_AI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memori_ai_saham_alpaca.json")


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


SYSTEM_PROMPT_SAHAM = """Kamu adalah asisten analisis saham AS & crypto di dalam sebuah aplikasi pembanding. Tugasmu membantu pengguna memahami data harga yang sedang mereka bandingkan.

Data saham/crypto yang sedang dibandingkan pengguna saat ini (data harga dari Alpaca Market Data API):
{konteks}
{blok_preferensi}
{blok_dokumen}
Instruksi:
- PENTING: aplikasi ini TIDAK punya data fundamental/laporan keuangan (PER, PBV, ROE, EPS, dividend, dsb) — semua rasio itu N/A. Kalau pengguna tanya soal itu, katakan terus terang datanya belum tersedia di aplikasi ini, jangan mengarang angka.
- Kamu cuma punya data harga terkini, harga kemarin, dan 52-week high/low. Analisis dari situ (posisi harga relatif terhadap 52W high/low, arah pergerakan sederhana), plus wawasan umum yang kamu tahu soal perusahaan/coin tersebut secara kualitatif — tapi jelaskan mana yang data aktual vs pengetahuan umum.
- Berikan analisis yang seimbang: sebutkan potensi kelebihan DAN risiko/kekurangan, bukan cuma satu sisi.
- Ini BUKAN rekomendasi beli/jual yang pasti — selalu jelaskan bahwa keputusan akhir ada di tangan pengguna.
- Jangan pernah mengklaim kepastian arah harga di masa depan, apalagi untuk crypto yang sangat volatil.
- Kalau ada catatan preferensi pengguna di atas, sesuaikan gaya jawabanmu dengan itu.
- Jawab dalam Bahasa Indonesia, ringkas dan jelas, boleh pakai bullet point kalau perlu.
"""


def bangun_konteks_saham(data_semua: dict) -> str:
    baris = []
    for kode, d in data_semua.items():
        h52 = d.get("52W High")
        l52 = d.get("52W Low")
        h52_txt = f"{h52}" if h52 is not None else "N/A"
        l52_txt = f"{l52}" if l52 is not None else "N/A"
        baris.append(
            f"- {d['Nama']} ({kode}, {d['Tipe']}): Harga {d['Mata Uang']} {d['Harga']}, "
            f"Harga kemarin {d.get('Harga Kemarin')}, 52W High {h52_txt}, 52W Low {l52_txt} "
            f"(rasio fundamental: N/A, tidak tersedia dari Alpaca)"
        )
    return "\n".join(baris)


if "riwayat_chat_saham" not in st.session_state:
    memori_awal = muat_memori_ai()
    st.session_state.riwayat_chat_saham = memori_awal["riwayat"]
    st.session_state.catatan_preferensi_ai = memori_awal["catatan_preferensi"]

if "catatan_preferensi_ai" not in st.session_state:
    st.session_state.catatan_preferensi_ai = ""

SARAN_PROMPT_AI = [
    ("📊", "Bandingkan posisi harga saham-saham ini vs 52W high/low"),
    ("⚠️", "Apa risiko utama dari saham/crypto ini?"),
    ("💡", "Jelaskan model bisnis masing-masing secara umum"),
    ("📈", "Mana yang pergerakan harganya paling volatil?"),
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
                "Tulis gaya analisis yang kamu suka (mis. 'fokus ke risiko volatilitas', 'jelasin singkat pakai bullet'). "
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