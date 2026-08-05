"""
Дашборд анализа расхождений по СКЮ
Автор: сгенерировано с помощью Claude
"""

import io
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

# ──────────────────────────────────────────────────────────────────────────
# КОНФИГУРАЦИЯ СТРАНИЦЫ
# ──────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Аналитика расхождений СКЮ",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Google Sheet по умолчанию (та, что прислал пользователь)
DEFAULT_SHEET_ID = "1xpiftC3wy1QRDdBxklSbgl5Ph4eW0wGcl8as9mIZXuU"
DEFAULT_GID = "447006824"
DEFAULT_SHEET_NAME = "По товарная сверка"

INTERNAL_COLS = [
    "sku", "magnit_code", "barcode", "description",
    "received", "shipped", "stock", "lost", "discrepancy",
]
DISPLAY_NAMES = {
    "sku": "СКЮ",
    "magnit_code": "Код Магнита",
    "barcode": "Баркод",
    "description": "Описания",
    "received": "Принято",
    "shipped": "Отгруженно",
    "stock": "Сток",
    "lost": "Потеряно",
    "discrepancy": "Рассхождения",
}
COLUMN_ALIASES = {
    "sku": ["скю", "sku"],
    "magnit_code": ["код магнита", "магнит"],
    "barcode": ["баркод", "штрихкод", "barcode"],
    "description": ["описани"],
    "received": ["принято"],
    "shipped": ["отгружен"],
    "stock": ["сток"],
    "lost": ["потер"],
    "discrepancy": ["рассхожд", "расхожд"],
}
NUMERIC_COLS = ["received", "shipped", "stock", "lost", "discrepancy"]

# ──────────────────────────────────────────────────────────────────────────
# СТИЛИ / АНИМАЦИИ
# ──────────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&display=swap');

    html, body, [class*="css"]  {
        font-family: 'Manrope', sans-serif;
    }

    .stApp {
        background: radial-gradient(circle at top left, #10151f 0%, #0b0f17 60%, #05070b 100%);
    }

    /* Заголовок */
    .hero {
        padding: 28px 34px;
        border-radius: 20px;
        background: linear-gradient(120deg, #7C3AED 0%, #4338CA 45%, #0EA5E9 100%);
        box-shadow: 0 20px 45px -15px rgba(76, 29, 149, 0.55);
        animation: fadeInDown 0.7s ease;
        margin-bottom: 24px;
    }
    .hero h1 {
        color: white;
        font-weight: 800;
        font-size: 34px;
        margin: 0;
        letter-spacing: -0.5px;
    }
    .hero p {
        color: rgba(255,255,255,0.85);
        margin: 6px 0 0 0;
        font-size: 15px;
    }

    @keyframes fadeInDown {
        from { opacity: 0; transform: translateY(-16px); }
        to   { opacity: 1; transform: translateY(0); }
    }
    @keyframes fadeInUp {
        from { opacity: 0; transform: translateY(16px); }
        to   { opacity: 1; transform: translateY(0); }
    }
    @keyframes pulse {
        0% { box-shadow: 0 0 0 0 rgba(124, 58, 237, 0.35); }
        70% { box-shadow: 0 0 0 12px rgba(124, 58, 237, 0); }
        100% { box-shadow: 0 0 0 0 rgba(124, 58, 237, 0); }
    }

    /* KPI карточки */
    .kpi-card {
        border-radius: 18px;
        padding: 20px 22px;
        background: linear-gradient(160deg, rgba(255,255,255,0.06), rgba(255,255,255,0.02));
        border: 1px solid rgba(255,255,255,0.08);
        animation: fadeInUp 0.6s ease both;
        transition: transform 0.25s ease, border-color 0.25s ease;
    }
    .kpi-card:hover {
        transform: translateY(-4px);
        border-color: rgba(124, 58, 237, 0.5);
    }
    .kpi-label {
        color: rgba(255,255,255,0.55);
        font-size: 13px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.6px;
        margin-bottom: 6px;
    }
    .kpi-value {
        color: #ffffff;
        font-size: 30px;
        font-weight: 800;
        line-height: 1.1;
    }
    .kpi-sub {
        margin-top: 6px;
        font-size: 13px;
        font-weight: 600;
    }
    .kpi-sub.pos { color: #34D399; }
    .kpi-sub.neg { color: #F87171; }
    .kpi-sub.neutral { color: #FBBF24; }

    /* Прогресс-полоски аналитики */
    .prog-wrap {
        background: rgba(255,255,255,0.06);
        border-radius: 999px;
        height: 10px;
        width: 100%;
        overflow: hidden;
        margin-top: 8px;
    }
    .prog-bar {
        height: 100%;
        border-radius: 999px;
        animation: growBar 1.1s cubic-bezier(.22,1,.36,1) both;
    }
    @keyframes growBar {
        from { width: 0%; }
    }

    /* Кнопки фильтра */
    div.stButton > button {
        border-radius: 12px !important;
        font-weight: 700 !important;
        border: 1px solid rgba(255,255,255,0.12) !important;
        transition: all 0.2s ease !important;
    }
    div.stButton > button:hover {
        transform: translateY(-2px);
        animation: pulse 1.2s infinite;
    }

    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0d1017 0%, #070910 100%);
        border-right: 1px solid rgba(255,255,255,0.06);
    }

    .badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 999px;
        font-size: 12px;
        font-weight: 700;
    }
    .badge.excess { background: rgba(52, 211, 153, 0.15); color: #34D399; }
    .badge.short  { background: rgba(248, 113, 113, 0.15); color: #F87171; }
    .badge.zero   { background: rgba(148, 163, 184, 0.15); color: #94A3B8; }

    footer {visibility: hidden;}
    </style>
    """,
    unsafe_allow_html=True,
)

# ──────────────────────────────────────────────────────────────────────────
# ЗАГРУЗКА И НОРМАЛИЗАЦИЯ ДАННЫХ
# ──────────────────────────────────────────────────────────────────────────
def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Приводит любые заголовки к внутренним именам по ключевым словам."""
    rename_map = {}
    used = set()
    for col in df.columns:
        low = str(col).strip().lower()
        for internal, keywords in COLUMN_ALIASES.items():
            if internal in used:
                continue
            if any(kw in low for kw in keywords):
                rename_map[col] = internal
                used.add(internal)
                break
    df = df.rename(columns=rename_map)

    # добавляем недостающие колонки как пустые
    for internal in INTERNAL_COLS:
        if internal not in df.columns:
            df[internal] = 0

    df = df[[c for c in INTERNAL_COLS]]
    return df


def clean_numeric(series: pd.Series) -> pd.Series:
    series = (
        series.astype(str)
        .str.replace("\xa0", "", regex=False)
        .str.replace(" ", "", regex=False)
        .str.replace(",", ".", regex=False)
        .str.strip()
    )
    series = series.replace({"": "0", "nan": "0", "None": "0", "-": "0"})
    return pd.to_numeric(series, errors="coerce").fillna(0)


def finalize(df: pd.DataFrame) -> pd.DataFrame:
    df = normalize_columns(df)
    for col in NUMERIC_COLS:
        df[col] = clean_numeric(df[col])
    for col in ["sku", "magnit_code", "barcode", "description"]:
        df[col] = df[col].fillna("0").astype(str).str.strip()
        df.loc[df[col].isin(["", "nan", "None"]), col] = "0"

    for col in NUMERIC_COLS:
        df[col] = df[col].round(0).astype("int64")

    def category(x):
        if x < 0:
            return "Излишки"
        elif x > 0:
            return "Недостачи"
        return "Без расхождений"

    df["category"] = df["discrepancy"].apply(category)
    return df.reset_index(drop=True)


@st.cache_data(ttl=300, show_spinner=False)
def load_from_google_sheet(sheet_id: str, gid: str) -> pd.DataFrame:
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    if resp.text.strip().lower().startswith("<!doctype") or "<html" in resp.text[:200].lower():
        raise ValueError("Таблица недоступна по ссылке (нет доступа 'Anyone with the link').")
    raw = pd.read_csv(io.StringIO(resp.text))
    return finalize(raw)


@st.cache_data(show_spinner=False)
def load_from_upload(file) -> pd.DataFrame:
    if file.name.lower().endswith(".csv"):
        raw = pd.read_csv(file)
    else:
        raw = pd.read_excel(file)
    return finalize(raw)


@st.cache_data(show_spinner=False)
def load_sample() -> pd.DataFrame:
    raw = pd.read_csv("data/sample_data.csv")
    return finalize(raw)


def to_excel_bytes(sheets: dict) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        workbook = writer.book
        header_fmt = workbook.add_format(
            {
                "bold": True,
                "bg_color": "#4338CA",
                "font_color": "white",
                "border": 1,
                "align": "center",
                "valign": "vcenter",
            }
        )
        pos_fmt = workbook.add_format({"font_color": "#0F9D58"})
        neg_fmt = workbook.add_format({"font_color": "#D93025"})

        for sheet_name, data in sheets.items():
            display_df = data.rename(columns=DISPLAY_NAMES)
            display_df = display_df.drop(columns=["category"], errors="ignore")
            display_df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
            ws = writer.sheets[sheet_name[:31]]
            for i, col in enumerate(display_df.columns):
                ws.write(0, i, col, header_fmt)
                width = max(14, min(46, int(display_df[col].astype(str).str.len().max() or 14) + 2))
                ws.set_column(i, i, width)
            if "Рассхождения" in display_df.columns:
                col_idx = list(display_df.columns).index("Рассхождения")
                ws.conditional_format(
                    1, col_idx, len(display_df), col_idx,
                    {"type": "cell", "criteria": "<", "value": 0, "format": neg_fmt},
                )
                ws.conditional_format(
                    1, col_idx, len(display_df), col_idx,
                    {"type": "cell", "criteria": ">", "value": 0, "format": pos_fmt},
                )
    return output.getvalue()


# ──────────────────────────────────────────────────────────────────────────
# SIDEBAR — ИСТОЧНИК ДАННЫХ
# ──────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Источник данных")
    source = st.radio(
        "Откуда брать данные",
        ["Google Таблица", "Загрузить файл", "Демо-данные"],
        index=0,
        label_visibility="collapsed",
    )

    df = None
    error_msg = None

    if source == "Google Таблица":
        sheet_id = st.text_input("ID таблицы (из URL)", value=DEFAULT_SHEET_ID)
        gid = st.text_input("GID листа (в конце ссылки после gid=)", value=DEFAULT_GID)
        st.caption(f"Лист: **{DEFAULT_SHEET_NAME}**")
        st.caption("⚠️ Таблица должна быть доступна по ссылке: «Все у кого есть ссылка — Читатель».")
        col_a, col_b = st.columns(2)
        with col_a:
            reload_clicked = st.button("🔄 Обновить", use_container_width=True)
        with col_b:
            if st.button("🗑️ Сброс кэша", use_container_width=True):
                st.cache_data.clear()
                st.rerun()
        if reload_clicked:
            st.cache_data.clear()
        try:
            df = load_from_google_sheet(sheet_id.strip(), gid.strip())
        except Exception as e:
            error_msg = str(e)

    elif source == "Загрузить файл":
        uploaded = st.file_uploader("CSV или Excel файл", type=["csv", "xlsx", "xls"])
        if uploaded:
            try:
                df = load_from_upload(uploaded)
            except Exception as e:
                error_msg = str(e)

    else:
        df = load_sample()

    if error_msg:
        st.error(f"Не удалось загрузить: {error_msg}")
        st.info("Использую демо-данные, пока источник недоступен.")
        df = load_sample()

    if df is None:
        st.warning("Загрузите данные, чтобы увидеть дашборд.")
        st.stop()

    st.markdown("---")
    st.markdown("### 🔍 Поиск и фильтры")
    search = st.text_input("Поиск (СКЮ / код / баркод / название)")

    sort_options = {
        "Без сортировки": None,
        "По модулю расхождения ↓": "abs_disc_desc",
        "Излишки сначала": "excess_first",
        "Недостачи сначала": "shortage_first",
    }
    sort_choice = st.selectbox("Сортировка", list(sort_options.keys()))

# ──────────────────────────────────────────────────────────────────────────
# ФИЛЬТР ПО ТИПУ РАСХОЖДЕНИЯ (КНОПКИ)
# ──────────────────────────────────────────────────────────────────────────
if "filter_mode" not in st.session_state:
    st.session_state.filter_mode = "all"

st.markdown(
    """
    <div class="hero">
        <h1>📦 Аналитика расхождений СКЮ</h1>
        <p>Сверка: Принято → Отгружено → Сток → Потери → Расхождения</p>
    </div>
    """,
    unsafe_allow_html=True,
)

btn_cols = st.columns(4)
labels = [
    ("all", "📊 Все позиции", "secondary"),
    ("excess", "📈 Излишки (—)", "secondary"),
    ("shortage", "📉 Недостачи (+)", "secondary"),
    ("loss", "⚠️ С потерями", "secondary"),
]
for i, (key, label, _) in enumerate(labels):
    btn_type = "primary" if st.session_state.filter_mode == key else "secondary"
    if btn_cols[i].button(label, use_container_width=True, type=btn_type, key=f"btn_{key}"):
        st.session_state.filter_mode = key

mode = st.session_state.filter_mode

# ──────────────────────────────────────────────────────────────────────────
# ПРИМЕНЕНИЕ ФИЛЬТРОВ
# ──────────────────────────────────────────────────────────────────────────
filtered = df.copy()

if mode == "excess":
    filtered = filtered[filtered["discrepancy"] < 0]
elif mode == "shortage":
    filtered = filtered[filtered["discrepancy"] > 0]
elif mode == "loss":
    filtered = filtered[filtered["lost"] > 0]

if search:
    s = search.strip().lower()
    mask = (
        filtered["sku"].str.lower().str.contains(s, na=False)
        | filtered["magnit_code"].str.lower().str.contains(s, na=False)
        | filtered["barcode"].str.lower().str.contains(s, na=False)
        | filtered["description"].str.lower().str.contains(s, na=False)
    )
    filtered = filtered[mask]

sort_key = sort_options[sort_choice]
if sort_key == "abs_disc_desc":
    filtered = filtered.reindex(filtered["discrepancy"].abs().sort_values(ascending=False).index)
elif sort_key == "excess_first":
    filtered = filtered.sort_values("discrepancy", ascending=True)
elif sort_key == "shortage_first":
    filtered = filtered.sort_values("discrepancy", ascending=False)

# ──────────────────────────────────────────────────────────────────────────
# АНАЛИТИКА (ПРОЦЕНТЫ)
# ──────────────────────────────────────────────────────────────────────────
total = len(df)
excess_n = int((df["discrepancy"] < 0).sum())
shortage_n = int((df["discrepancy"] > 0).sum())
zero_n = total - excess_n - shortage_n
loss_n = int((df["lost"] > 0).sum())

pct_excess = excess_n / total * 100 if total else 0
pct_shortage = shortage_n / total * 100 if total else 0
pct_zero = zero_n / total * 100 if total else 0
pct_loss = loss_n / total * 100 if total else 0

sum_excess_qty = int(df.loc[df["discrepancy"] < 0, "discrepancy"].sum())
sum_shortage_qty = int(df.loc[df["discrepancy"] > 0, "discrepancy"].sum())
sum_lost_qty = int(df["lost"].sum())

st.markdown("### 📈 Ключевые показатели")
kpi_cols = st.columns(5)
kpi_data = [
    ("Всего СКЮ", f"{total:,}".replace(",", " "), None, None),
    ("Излишки", f"{excess_n:,}".replace(",", " "), f"{pct_excess:.1f}% · {sum_excess_qty:,} шт".replace(",", " "), "pos"),
    ("Недостачи", f"{shortage_n:,}".replace(",", " "), f"{pct_shortage:.1f}% · +{sum_shortage_qty:,} шт".replace(",", " "), "neg"),
    ("Без расхождений", f"{zero_n:,}".replace(",", " "), f"{pct_zero:.1f}%", "neutral"),
    ("С потерями", f"{loss_n:,}".replace(",", " "), f"{pct_loss:.1f}% · {sum_lost_qty:,} шт".replace(",", " "), "neg"),
]
for col, (label, value, sub, cls) in zip(kpi_cols, kpi_data):
    sub_html = f'<div class="kpi-sub {cls}">{sub}</div>' if sub else ""
    col.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            {sub_html}
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)

# Прогресс-бары долей
prog_col1, prog_col2, prog_col3 = st.columns(3)
progress_data = [
    (prog_col1, "Излишки", pct_excess, "#34D399"),
    (prog_col2, "Недостачи", pct_shortage, "#F87171"),
    (prog_col3, "Потери", pct_loss, "#FBBF24"),
]
for col, label, pct, color in progress_data:
    col.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-label">Доля: {label}</div>
            <div class="kpi-value" style="font-size:24px;">{pct:.1f}%</div>
            <div class="prog-wrap">
                <div class="prog-bar" style="width:{pct:.1f}%; background:{color};"></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────────────────
# ГРАФИКИ
# ──────────────────────────────────────────────────────────────────────────
chart_col1, chart_col2 = st.columns([1, 1.4])

with chart_col1:
    st.markdown("#### 🍩 Структура расхождений")
    donut_df = pd.DataFrame(
        {
            "Категория": ["Излишки", "Недостачи", "Без расхождений"],
            "Кол-во": [excess_n, shortage_n, zero_n],
        }
    )
    fig_donut = px.pie(
        donut_df,
        names="Категория",
        values="Кол-во",
        hole=0.58,
        color="Категория",
        color_discrete_map={
            "Излишки": "#34D399",
            "Недостачи": "#F87171",
            "Без расхождений": "#94A3B8",
        },
    )
    fig_donut.update_traces(
        textposition="outside",
        textinfo="percent+label",
        pull=[0.03, 0.03, 0],
        marker=dict(line=dict(color="#0b0f17", width=2)),
    )
    fig_donut.update_layout(
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="white",
        margin=dict(t=10, b=10, l=10, r=10),
        height=340,
        transition_duration=500,
    )
    st.plotly_chart(fig_donut, use_container_width=True)

with chart_col2:
    st.markdown("#### 🔝 Топ-15 позиций по модулю расхождения")
    top = df.reindex(df["discrepancy"].abs().sort_values(ascending=False).index).head(15).copy()
    top["label"] = top["description"].str.slice(0, 38) + top["description"].apply(lambda x: "…" if len(x) > 38 else "")
    top["sign"] = top["discrepancy"].apply(lambda x: "Излишек" if x < 0 else ("Недостача" if x > 0 else "Норма"))
    fig_bar = px.bar(
        top.sort_values("discrepancy"),
        x="discrepancy",
        y="label",
        orientation="h",
        color="sign",
        color_discrete_map={"Излишек": "#34D399", "Недостача": "#F87171", "Норма": "#94A3B8"},
        labels={"discrepancy": "Расхождение, шт", "label": "", "sign": "Тип"},
    )
    fig_bar.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=10, b=10, l=10, r=10),
        height=340,
        transition_duration=500,
    )
    fig_bar.update_xaxes(gridcolor="rgba(255,255,255,0.08)")
    st.plotly_chart(fig_bar, use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────────────────
# ТАБЛИЦА ДАННЫХ
# ──────────────────────────────────────────────────────────────────────────
mode_titles = {
    "all": "Все позиции",
    "excess": "Излишки (расхождение со знаком «−»)",
    "shortage": "Недостачи (расхождение положительное)",
    "loss": "Позиции с потерями",
}
st.markdown(f"### 📋 {mode_titles[mode]} · найдено {len(filtered):,}".replace(",", " "))

display_df = filtered.rename(columns=DISPLAY_NAMES).drop(columns=["category"], errors="ignore")


def highlight_disc(val):
    if isinstance(val, (int, float)):
        if val < 0:
            return "color:#34D399; font-weight:700;"
        elif val > 0:
            return "color:#F87171; font-weight:700;"
    return ""


styled = display_df.style.applymap(highlight_disc, subset=["Рассхождения"])
st.dataframe(styled, use_container_width=True, height=420, hide_index=True)

# ──────────────────────────────────────────────────────────────────────────
# ЭКСПОРТ В EXCEL
# ──────────────────────────────────────────────────────────────────────────
st.markdown("### 📤 Выгрузка в Excel")
exp_col1, exp_col2, exp_col3 = st.columns(3)

with exp_col1:
    excel_all = to_excel_bytes(
        {
            "Все": df,
            "Излишки": df[df["discrepancy"] < 0],
            "Недостачи": df[df["discrepancy"] > 0],
            "Потери": df[df["lost"] > 0],
        }
    )
    st.download_button(
        "⬇️ Полный отчёт (все листы)",
        data=excel_all,
        file_name=f"raskhozhdeniya_full_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

with exp_col2:
    excel_current = to_excel_bytes({mode_titles[mode][:31]: filtered})
    st.download_button(
        "⬇️ Текущий фильтр",
        data=excel_current,
        file_name=f"raskhozhdeniya_{mode}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

with exp_col3:
    csv_bytes = display_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "⬇️ Текущий фильтр (CSV)",
        data=csv_bytes,
        file_name=f"raskhozhdeniya_{mode}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
        use_container_width=True,
    )

st.markdown(
    """
    <div style="text-align:center; color:rgba(255,255,255,0.35); margin-top:36px; font-size:12px;">
        Дашборд обновляется из Google Таблицы каждые 5 минут · Сделано на Streamlit
    </div>
    """,
    unsafe_allow_html=True,
)
