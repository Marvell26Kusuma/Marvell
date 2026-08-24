import os
import json
import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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
# 1. Konfigurasi Tampilan Halaman
# ============================================================
st.set_page_config(page_title="Pembanding Saham", layout="wide", page_icon="chart_with_upwards_trend")
st.title("Pembanding Laporan Keuangan Saham")
st.caption("Bandingkan rasio keuangan beberapa emiten sekaligus — cari dari 900+ saham IDX, pilih dari kategori sektor, dan tampilkan grafik per rasio.")

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

    /* Cegah scroll horizontal — panel Asisten AI yang digeser ke luar layar
       (translateX) tetap dihitung lebarnya oleh browser kalau ini tidak dikunci.
       Ditarget ke beberapa kemungkinan container scroll Streamlit sekaligus,
       karena versi Streamlit berbeda-beda punya elemen scroll utama yang beda. */
    html {{
        overflow-x: hidden !important;
        max-width: 100vw !important;
        background-color: {app_bg} !important;
        color-scheme: dark; /* cegah Chrome/browser auto-invert warna halaman yang sudah gelap */
    }}
    body {{
        overflow-x: hidden !important;
        background-color: {app_bg} !important;
        overscroll-behavior-y: none; /* cegah flash putih pas rubber-band scroll di iOS/Android */
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

    /* Sembunyikan chrome bawaan Streamlit supaya lebih clean */
    #MainMenu, footer, [data-testid="stDecoration"] {{
        visibility: hidden;
        height: 0;
    }}

    /* Judul & heading — lebih tegas, spasi lebih rapi */
    h1 {{ font-weight: 700; letter-spacing: -0.02em; }}
    h2, h3 {{ font-weight: 600; letter-spacing: -0.01em; }}

    /* Tombol — rounded, border tipis, background gelap konsisten (bukan putih bawaan) */
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

    /* Expander — background gelap (bawaannya putih kalau tidak di-set) */
    [data-testid="stExpander"] {{
        background-color: rgba(255,255,255,0.02);
        border: 1px solid rgba(128,128,128,0.15);
        border-radius: 10px;
    }}
    [data-testid="stExpander"] summary {{
        background-color: transparent !important;
    }}

    /* Tabs — garis bawah lebih halus */
    [data-baseweb="tab-list"] {{
        gap: 4px;
    }}
    [data-baseweb="tab"] {{
        border-radius: 8px 8px 0 0;
    }}

    /* Input, selectbox, multiselect — background gelap konsisten (BaseWeb default-nya putih) */
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
    /* "Chip" pilihan yang sudah dipilih di dalam multiselect */
    [data-baseweb="tag"] {{
        background-color: rgba(41,98,255,0.25) !important;
    }}

    /* Menu dropdown/popover BaseWeb dirender di luar pohon DOM utama (portal ke
       document.body), jadi harus ditarget terpisah supaya ikut gelap juga —
       ini penyebab utama kotak putih nyala pas buka dropdown di HP. */
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

    /* Metric — angka lebih tegas */
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
PATH_CSV_SAHAM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daftar_saham_idx.csv")


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
        "pastikan file CSV diletakkan satu folder dengan `pembanding_saham.py`."
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


# ============================================================
# 3. State: daftar saham yang sedang dibandingkan
# ============================================================
if "daftar_saham" not in st.session_state:
    st.session_state.daftar_saham = ["BBCA.JK", "BBRI.JK"]


def tambah_saham(kode: str):
    kode = kode.strip().upper()
    if kode and kode not in st.session_state.daftar_saham:
        st.session_state.daftar_saham.append(kode)


def hapus_saham(kode: str):
    if kode in st.session_state.daftar_saham:
        st.session_state.daftar_saham.remove(kode)


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
if not st.session_state.daftar_saham:
    st.sidebar.info("Belum ada saham. Tambahkan minimal 2 saham di atas.")
else:
    for kode in st.session_state.daftar_saham:
        c1, c2 = st.sidebar.columns([4, 1])
        c1.write(f"• **{kode}**")
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
    /* Sisakan ruang di kanan supaya konten utama tidak ketutup panel AI yang fixed.
       Selalu di-render (bukan kondisional) supaya transition-nya jalan mulus
       saat panel dibuka/ditutup, bukan lompat instan. */
    [data-testid="stMainBlockContainer"], .main .block-container {{
        padding-right: {PADDING_KANAN_AKTIF}px !important;
        transition: padding-right 0.18s cubic-bezier(0.2, 0, 0.2, 1);
    }}

    /* Cegah elemen manapun "tembus" keluar tepi layar HP akibat padding/border
       yang menambah lebar di luar perhitungan width normal. */
    *, *::before, *::after {{
        box-sizing: border-box;
    }}

    /* Di layar sempit (HP), panel AI jadi overlay penuh (bukan sisip di
       samping), jadi konten utama TIDAK perlu diberi ruang kosong di
       kanan — kalau tetap dipaksa, layar HP jadi kepencet sempit sekali. */
    @media (max-width: 768px) {{
        [data-testid="stMainBlockContainer"], .main .block-container {{
            padding-right: 1rem !important;
            padding-left: 1rem !important;
        }}

        /* Streamlit otomatis nge-stack st.columns() ke bawah kalau layar
           sempit — di sini dipaksa TETAP sejajar (nowrap) dan boleh
           discroll ke samping, bukan ditumpuk ke bawah semua. */
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

        /* Elemen lebar (dataframe, chart, gambar) dikunci max 100% lebar
           layar supaya tidak melebar keluar (tembus tepi) di HP. */
        [data-testid="stDataFrame"],
        [data-testid="stImage"],
        iframe,
        .element-container {{
            max-width: 100% !important;
        }}

        h1 {{ font-size: 1.6rem !important; }}
        h2 {{ font-size: 1.25rem !important; }}
    }}

    /* Scroll sentuhan yang lebih halus di semua elemen yang bisa digeser */
    .scroll-container, [data-testid="stHorizontalBlock"], [data-testid="stDataFrame"] {{
        -webkit-overflow-scrolling: touch;
        scroll-behavior: smooth;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# Backdrop khusus HP: kalau panel AI kebuka di layar sempit, area di luar
# panel jadi bisa diklik/ditap buat nutup panel-nya lagi (klik di mana pun
# selain panel = otomatis uncheck checkbox "Tampilkan Asisten AI" di sidebar).
# Pakai components.html (bukan st.markdown) karena butuh <script> yang bisa
# benar-benar dieksekusi browser, lalu dari situ "menjangkau" dokumen utama
# lewat window.parent supaya bisa membuat backdrop & mengklik checkbox aslinya.
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

            data = {
                "Nama": info.get("shortName", ticker),
                "Ticker": ticker.upper(),
                "Mata Uang": info.get("currency", ""),
                "Harga": fmt(info.get("currentPrice") or info.get("regularMarketPrice"), 0),
                "Market Cap": info.get("marketCap"),

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


    TIMEFRAME_HARGA = {
        "Harian": {"interval": "1d", "resample": None},
        "Mingguan": {"interval": "1wk", "resample": None},
        "Bulanan": {"interval": "1mo", "resample": None},
        "Tahunan": {"interval": "3mo", "resample": "YE"},  # candle kuartalan diagregasi jadi tahunan
    }


    @st.cache_data(ttl=600, show_spinner=False)
    def ambil_data_harga(ticker: str, periode: str, interval: str, resample):
        try:
            data = yf.Ticker(ticker, session=dapatkan_sesi_yf()).history(period=periode, interval=interval)
            if data is None or data.empty:
                return None
            data = data[["Open", "High", "Low", "Close", "Volume"]].dropna()

            if resample:
                data = data.resample(resample).agg({
                    "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum",
                }).dropna()

            data = data.reset_index()
            kolom_waktu = data.columns[0]
            data = data.rename(columns={kolom_waktu: "Waktu"})
            return data
        except Exception:
            return None


    def render_tradingview_chart(
        df: pd.DataFrame, ticker: str, tinggi: int = 560, chart_key: str = "tvchart",
        warna_naik: str = "#26a69a", warna_turun: str = "#ef5350", warna_bg_chart: str = "#131722",
    ):
        """Render candlestick + volume pakai library asli TradingView: Lightweight Charts
        (open-source, MIT license, dipakai TradingView sendiri untuk versi gratisnya).
        Ini memberi interaksi native TradingView: scroll = zoom, drag = pan, drag di
        sumbu harga/waktu = rescale, crosshair, dsb — tanpa perlu diakali lewat Plotly.
        """
        df_js = df.copy()
        df_js["time"] = pd.to_datetime(df_js["Waktu"]).dt.strftime("%Y-%m-%d")
        df_js["PctChange"] = df_js["Close"].pct_change() * 100  # naik/turun vs candle sebelumnya

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

                // Skala volume dibuat overlay terpisah, hanya menempati ~18% bawah
                // chart, dan label angkanya disembunyikan supaya tidak tabrakan
                // dengan angka pada skala harga (kanan).
                chart.priceScale("vol").applyOptions({{
                    scaleMargins: {{ top: 0.82, bottom: 0 }},
                    visible: false,
                }});

                chart.timeScale().fitContent();

                // Legend OHLC: menampilkan Open/High/Low/Close + persentase naik/turun
                // vs candle sebelumnya, mengikuti posisi kursor. Field custom (pctChange)
                // dicari lewat lookup map karena Lightweight Charts membuang field di
                // luar OHLC saat data dikembalikan lewat event crosshair.
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
                    tampilkanLegend(barTerakhir, barTerakhir.pctChange);  // tampil default: candle terakhir
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

                // ================================================================
                // Menu klik-kanan ala TradingView: reset skala harga, reset skala
                // waktu, toggle skala logaritmik, unduh chart sebagai gambar.
                // ================================================================
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
                    link.download = "{ticker}_chart.png";
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
        # Dibuat sebagai satu baris tanpa indentasi/newline supaya tidak
        # dianggap code block oleh parser Markdown Streamlit.
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
    # 9b. Grafik Pergerakan Harga (data Yahoo Finance, delay ~15-20 menit)
    # ============================================================
    st.subheader("Pergerakan Harga Saham")
    st.caption("Data harga bersumber dari Yahoo Finance dan biasanya memiliki delay ±15-20 menit dari harga real-time bursa — bukan data streaming langsung.")

    if AUTOREFRESH_TERSEDIA:
        st_autorefresh(interval=10 * 60 * 1000, key="autorefresh_harga")  # otomatis, tanpa perlu diklik
        st.caption("Auto-refresh tiap 10 menit — aktif otomatis.")
    else:
        st.caption("Auto-refresh butuh: `pip install streamlit-autorefresh`")

    if "tickers_chart_terpilih" not in st.session_state:
        st.session_state.tickers_chart_terpilih = [list(data_semua.keys())[0]]

    opsi_chart = list(dict.fromkeys(list(data_semua.keys()) + st.session_state.tickers_chart_terpilih))

    tickers_dipilih = st.multiselect(
        "Pilih saham untuk chart (bisa lebih dari satu untuk bandingin split-screen)",
        options=opsi_chart,
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

    OFFSET_PERUBAHAN = {
        "Harian": pd.DateOffset(days=1),
        "Mingguan": pd.DateOffset(weeks=1),
        "Bulanan": pd.DateOffset(months=1),
        "Tahunan": pd.DateOffset(years=1),
    }
    LABEL_PERUBAHAN = {
        "Harian": "1 hari terakhir",
        "Mingguan": "1 minggu terakhir",
        "Bulanan": "1 bulan terakhir",
        "Tahunan": "1 tahun terakhir",
    }


    def render_satu_panel_chart(ticker_chart: str, tinggi_chart: int):
        periode = "max"
        interval = konfig_tf["interval"]
        resample = konfig_tf["resample"]

        with st.spinner(f"Mengambil data harga {ticker_chart}..."):
            data_harga = ambil_data_harga(ticker_chart, periode, interval, resample)

        if data_harga is None or data_harga.empty or len(data_harga) <= 1:
            st.warning(f"Data harga untuk **{ticker_chart}** pada timeframe **{timeframe_terpilih}** tidak tersedia.")
            return

        harga_akhir = data_harga["Close"].iloc[-1]
        tanggal_terakhir = pd.to_datetime(data_harga["Waktu"].iloc[-1])
        tanggal_acuan = tanggal_terakhir - OFFSET_PERUBAHAN[timeframe_terpilih]
        data_sebelum_acuan = data_harga[pd.to_datetime(data_harga["Waktu"]) <= tanggal_acuan]
        harga_awal = data_sebelum_acuan["Close"].iloc[-1] if not data_sebelum_acuan.empty else data_harga["Close"].iloc[0]
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
                    <span style="font-size:15px; font-weight:500; color:#8a8f99;">({ticker_chart})</span>
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
                    {LABEL_PERUBAHAN[timeframe_terpilih]}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        render_tradingview_chart(
            data_harga, ticker_chart, tinggi=tinggi_chart, chart_key=f"{ticker_chart}_{timeframe_terpilih}",
            warna_naik=warna_candle_naik, warna_turun=warna_candle_turun, warna_bg_chart=warna_bg_chart,
        )


    if not tickers_dipilih:
        st.info("Pilih atau cari saham di atas untuk melihat grafik pergerakan harganya.")
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
            "Bisa pilih sampai 4 saham sekaligus untuk dibandingkan berdampingan (split-screen)."
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
PATH_MEMORI_AI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memori_ai_saham.json")


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
        pass  # gagal simpan bukan hal fatal, chat tetap jalan normal di sesi ini


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


if "riwayat_chat_saham" not in st.session_state:
    memori_awal = muat_memori_ai()
    st.session_state.riwayat_chat_saham = memori_awal["riwayat"]
    st.session_state.catatan_preferensi_ai = memori_awal["catatan_preferensi"]

if "catatan_preferensi_ai" not in st.session_state:
    st.session_state.catatan_preferensi_ai = ""

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

        # -- Panel dibuat fixed di sisi kanan layar (position:fixed), menyatu
        #    seperti sidebar bawaan Streamlit tapi di sisi kanan, memanjang
        #    penuh dari atas sampai bawah. Polos, tanpa efek dekoratif.
        #    Container ini SELALU di-render (tidak dibungkus if) supaya node-nya
        #    tetap ada di DOM — buka/tutup panel cuma menggeser transform & opacity,
        #    bukan memasang/melepas elemen, sehingga transisinya mulus (bukan lompat). --
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
            /* Di HP (layar sempit), panel jadi overlay penuh layar biar
               tetap enak dipakai — bukan kolom sempit 380px yang kegencet. */
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
            /* Chat input dibiarkan mengalir normal (bukan sticky/fixed) —
               nempel di posisi paling bawah dari urutan konten panel,
               bukan dipaksa "mengambang" secara visual. */
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

        # Saran cepat — hanya ditampilkan sebelum obrolan dimulai.
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

        prompt_saham = st.chat_input("Tanya soal saham ini...", key="chat_input_saham")
        if prompt_saham:
            _proses_prompt_ai(kotak_chat, prompt_saham)
            st.rerun()