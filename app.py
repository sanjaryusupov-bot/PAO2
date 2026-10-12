"""Дашборд «Аналитика расхождений СКЮ» — v3"""
import base64
import io
import json
from datetime import datetime

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
import streamlit.components.v1 as components

SHEET_ID = "1xpiftC3wy1QRDdBxklSbgl5Ph4eW0wGcl8as9mIZXuU"
GID = "447006824"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"
CACHE_TTL_SECONDS = 300

# ОКК: отдельная таблица «ФМСЖ Магнит Проблемные» (Тип расхождения / Разница)
OKK_SHEET_ID = "1NtUWK9MzQWK_TeaslgYLCtVBUZnE4Eg1FpXE_0_fAEg"
OKK_TABS = {
    "ФМСЖ Общее": "1884530113",
    "Местн. поставщик": "",   # ← вставьте gid этой вкладки (число после gid= в адресе вкладки)
}
OKK_COLS = ["Строка", "Источник", "№ накладной", "Дата", "ШК", "Наименование",
            "Тип расхождения", "Кол-во", "Комментарий"]
OKK_EXPORT = ["Строка", "ШК", "Наименование", "Тип расхождения", "Кол-во", "Комментарий"]
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

st.set_page_config(page_title="Аналитика расхождений СКЮ", page_icon="📦",
                   layout="wide", initial_sidebar_state="collapsed")

INTERNAL_COLS = ["sku", "magnit_code", "description", "received", "shipped", "stock", "lost", "discrepancy"]
DISPLAY_NAMES = {"sku": "СКЮ", "magnit_code": "Код Магнита", "description": "Описания",
                 "received": "Принято", "shipped": "Отгруженно", "stock": "Сток",
                 "lost": "Потеряно", "discrepancy": "Рассхождения"}
COLUMN_ALIASES = {"sku": ["скю", "sku"], "magnit_code": ["код магнита", "магнит"],
                  "description": ["описани"], "received": ["принято"], "shipped": ["отгружен"],
                  "stock": ["сток"], "lost": ["потер"], "discrepancy": ["рассхожд", "расхожд"]}
NUMERIC_COLS = ["received", "shipped", "stock", "lost", "discrepancy"]
GROUP_COLS = ["sku", "magnit_code", "description"]

# Демо-данные — только запасной вариант, если таблица недоступна
SAMPLE_DATA_CSV = """СКЮ,Код Магнита,Описания,Принято,Отгруженно,Сток,Потерянно,Рассхождения
1000000000000005264,1000585538,Пакет-майка M Cosmetic мал 36х60 УЗ,374750,270581,102600,1141,428
1000000000000020941,8000107234,LAF Набор заколок для волос №1 в асс УЗ,79763,801,78962,0,0
1000000000000008137,8000107235,LAF Крабик для волос Фигурный в асс УЗ,60013,4341,55499,0,173
1000000000000016630,8000107224,LAF Крабик для волос №1 13см в асс УЗ,59737,3492,55855,12,378
1000000000000015409,8000107223,LAF Крабик для волос №2 13см в асс УЗ,38695,2195,36507,12,-19
1000000000000027153,1000533997,LAF Матирующие салфетки зеленые 50 шт (СИ):3/501,24042,2159,21829,108,-54
1000000000000021332,8000003226,LAF Набор пуховка велюровая д/пудры 2шт треугол (СИ):4/1000,17053,10563,7159,132,-801
1000000000000018631,4000104284,LAF Резинки для волос 3 шт Color (СИ):4/1200,15701,2230,11655,0,1816
1000000000000005459,8000069635,SUNLIGHT Влажные салфетки Universal XXL 9шт УЗ,12144,14012,1186,171,-3225
1000000000000012660,1000529247,LOREAL Elseve Шампунь д/вол гиалуон Pure 400мл:6,7300,3171,3554,1061,-486
1000000000000015072,1000441981,SUNLIGHT Влажные салфетки карм Woman 2021 15х144 УЗ,7309,6980,326,210,-207
1000000000000010190,8000024698,LAF Набор резинок д/волос 2шт Бантики ДС5(СИ):6/480,7198,388,6810,0,0"""

# категория: (заголовок карточки, префикс файла, иконка, цвет 1, цвет 2, имя листа)
KINDS = {
    "all":      ("Всего СКЮ",       "vse_tovary",       "📦", "#6366F1", "#A78BFA", "Все товары"),
    "excess":   ("Излишки",         "izlishki",         "📈", "#16A34A", "#4ADE80", "Излишки"),
    "shortage": ("Недостачи",       "nedostachi",       "📉", "#DC2626", "#FB7185", "Недостачи"),
    "zero":     ("Без расхождений", "bez_rashozhdeniy", "✅", "#0891B2", "#22D3EE", "Без расхождений"),
    "loss":     ("С потерями",      "poteri",           "⚠️", "#D97706", "#FBBF24", "Потери"),
}

# ───────────────────────────── СТИЛИ ─────────────────────────────
# HTML внутри st.markdown — строго без отступов (иначе Markdown сделает из него код)
st.markdown("<style>" + "".join(
    f".st-key-card_{k}{{--c:{v[3]};--c2:{v[4]};}}" for k, v in KINDS.items()) + "</style>",
    unsafe_allow_html=True)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
[data-testid="stAppViewContainer"], [data-testid="stMain"], [data-testid="stHeader"] { background: transparent !important; }
.stApp {
background: radial-gradient(700px 450px at 12% 8%, rgba(139,92,246,.24), transparent 70%),
            radial-gradient(650px 420px at 90% 6%, rgba(34,211,238,.22), transparent 70%),
            radial-gradient(700px 450px at 60% 100%, rgba(244,114,182,.18), transparent 70%),
            #F6F4FF !important;
background-attachment: fixed !important;
}
@keyframes fadeUp { from { opacity:0; transform: translateY(16px); } to { opacity:1; transform:none; } }
@keyframes flow { to { background-position: 300% 0; } }
@keyframes pulse { 0%,100% { box-shadow: 0 0 0 0 rgba(74,222,128,.7); } 50% { box-shadow: 0 0 0 8px rgba(74,222,128,0); } }
@keyframes grow { from { width: 0; } }
.block-container { padding-top: 2rem; max-width: 1400px; }
h1, h2, h3, h4, p, span, label { color: #1E1B33; }
footer { visibility: hidden; }

/* HERO */
.hero {
display: flex; justify-content: space-between; align-items: center; gap: 24px; flex-wrap: wrap;
padding: 30px 36px; border-radius: 24px; color: #fff;
background: linear-gradient(120deg, #312E81, #6D28D9, #0EA5E9, #6D28D9, #312E81);
background-size: 300% 100%; animation: flow 14s linear infinite, fadeUp .6s ease;
box-shadow: 0 20px 50px rgba(79,70,229,.35);
}
.hero h1 { color: #fff; font-size: 32px; font-weight: 900; margin: 10px 0 4px; letter-spacing: -.5px; }
.hero p { color: #E0E7FF; margin: 0; font-size: 14px; }
.badge { display: inline-flex; align-items: center; gap: 8px; padding: 5px 14px; border-radius: 999px;
background: rgba(255,255,255,.16); border: 1px solid rgba(255,255,255,.3); font-size: 12px; font-weight: 700; color: #fff; }
.dot { width: 9px; height: 9px; border-radius: 50%; background: #4ADE80; animation: pulse 1.8s infinite; }
.dot.off { background: #FBBF24; animation: none; }
.hero-stats { display: flex; gap: 14px; }
.hero-stats div { padding: 12px 20px; border-radius: 16px; text-align: center;
background: rgba(255,255,255,.14); border: 1px solid rgba(255,255,255,.25); backdrop-filter: blur(8px); }
.hero-stats b { display: block; font-size: 22px; font-weight: 900; color: #fff; }
.hero-stats span { font-size: 11px; color: #C7D2FE; text-transform: uppercase; letter-spacing: .6px; }

/* КАРТОЧКИ-ВЫГРУЗКИ: сама карточка = контейнер, кнопка скачивания внутри */
[class*="st-key-card_"] {
position: relative; overflow: hidden; gap: .55rem !important;
padding: 20px 20px 16px; border-radius: 22px;
background: rgba(255,255,255,.82); backdrop-filter: blur(14px);
border: 1px solid rgba(124,58,237,.10); box-shadow: 0 8px 28px rgba(79,70,229,.10);
transition: transform .25s ease, box-shadow .25s ease; animation: fadeUp .6s ease both;
}
[class*="st-key-card_"]::before { content: ""; position: absolute; left: 0; right: 0; top: 0; height: 5px;
background: linear-gradient(90deg, var(--c), var(--c2)); }
[class*="st-key-card_"]:hover { transform: translateY(-6px); box-shadow: 0 22px 44px rgba(79,70,229,.22); }
.k-top { display: flex; align-items: center; gap: 10px; }
.k-ico { width: 38px; height: 38px; border-radius: 12px; display: grid; place-items: center; font-size: 18px;
background: linear-gradient(135deg, var(--c), var(--c2)); box-shadow: 0 6px 14px rgba(0,0,0,.15); }
.k-label { font-size: 12px; font-weight: 800; text-transform: uppercase; letter-spacing: .7px; color: #6B6690; }
.k-val { font-size: 32px; font-weight: 900; line-height: 1.1; margin-top: 4px;
background: linear-gradient(90deg, var(--c), var(--c2)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.k-val small { font-size: 14px; font-weight: 700; }
.k-sub { font-size: 12.5px; font-weight: 700; color: var(--c); }
.k-bar { height: 7px; border-radius: 99px; background: rgba(100,100,140,.12); overflow: hidden; margin: 4px 0 2px; }
.k-bar i { display: block; height: 100%; border-radius: 99px; background: linear-gradient(90deg, var(--c), var(--c2)); animation: grow 1.1s cubic-bezier(.22,1,.36,1) both; }
[class*="st-key-card_"] [data-testid="stDownloadButton"] button,
[class*="st-key-card_"] .stDownloadButton button {
width: 100%; border: none !important; border-radius: 12px !important; font-weight: 800 !important; color: #fff !important;
background: linear-gradient(90deg, var(--c), var(--c2)) !important; transition: all .2s ease !important;
}
[class*="st-key-card_"] [data-testid="stDownloadButton"] button:hover,
[class*="st-key-card_"] .stDownloadButton button:hover { filter: brightness(1.1); transform: translateY(-2px); box-shadow: 0 8px 18px rgba(0,0,0,.2); }
[class*="st-key-card_"] [data-testid="stDownloadButton"] button *, [class*="st-key-card_"] .stDownloadButton button * { color: #fff !important; }

/* ОБЩИЕ КНОПКИ */
div.stButton > button { border-radius: 14px !important; font-weight: 800 !important; background: #fff !important;
color: #4C1D95 !important; border: 1px solid rgba(124,58,237,.25) !important; transition: all .2s ease !important; padding: .55rem 1rem; }
div.stButton > button:hover { transform: translateY(-2px); border-color: #7C3AED !important; box-shadow: 0 8px 18px rgba(124,58,237,.25); }
div.stButton > button[kind="primary"] { background: linear-gradient(90deg, #7C3AED, #0EA5E9) !important; color: #fff !important; border: none !important; }
div.stButton > button[kind="primary"] * { color: #fff !important; }
.st-key-full_dl [data-testid="stDownloadButton"] button, .st-key-full_dl .stDownloadButton button,
[class*="st-key-filter_dl"] [data-testid="stDownloadButton"] button, [class*="st-key-filter_dl"] .stDownloadButton button {
width: 100%; border: none !important; border-radius: 14px !important; font-weight: 900 !important; color: #fff !important;
background: linear-gradient(90deg, #F59E0B, #EF4444, #EC4899) !important; padding: .7rem 1rem; box-shadow: 0 10px 24px rgba(239,68,68,.35);
}
[class*="st-key-filter_dl"] [data-testid="stDownloadButton"] button, [class*="st-key-filter_dl"] .stDownloadButton button { background: linear-gradient(90deg, #7C3AED, #0EA5E9) !important; box-shadow: 0 10px 24px rgba(79,70,229,.3); }
.st-key-full_dl button *, [class*="st-key-filter_dl"] button * { color: #fff !important; }

.sec { font-size: 20px; font-weight: 900; margin: 28px 0 10px; }
.sec small { font-size: 13px; font-weight: 600; color: #8B87AE; margin-left: 8px; }
.panel { padding: 8px 12px; border-radius: 22px; background: rgba(255,255,255,.82); border: 1px solid rgba(124,58,237,.10); box-shadow: 0 8px 28px rgba(79,70,229,.08); }
.strip { display: flex; gap: 14px; flex-wrap: wrap; margin: 6px 0 14px; }
.strip div { padding: 10px 18px; border-radius: 14px; background: rgba(255,255,255,.85); border: 1px solid rgba(124,58,237,.14);
font-size: 13.5px; color: #443F6B; }
.strip b { color: #1E1B33; font-size: 15px; }
section[data-testid="stSidebar"] { background: rgba(255,255,255,.95); }
</style>
""", unsafe_allow_html=True)


# ───────────────────── ЗАГРУЗКА / НОРМАЛИЗАЦИЯ ─────────────────────
def normalize_columns(d: pd.DataFrame) -> pd.DataFrame:
    rename_map, used = {}, set()
    for col in d.columns:
        low = str(col).strip().lower()
        for internal, kws in COLUMN_ALIASES.items():
            if internal not in used and any(k in low for k in kws):
                rename_map[col] = internal
                used.add(internal)
                break
    d = d.rename(columns=rename_map)
    for internal in INTERNAL_COLS:
        if internal not in d.columns:
            d[internal] = 0
    return d[INTERNAL_COLS]


def clean_numeric(s: pd.Series) -> pd.Series:
    s = (s.astype(str).str.replace("\xa0", "", regex=False).str.replace(" ", "", regex=False)
         .str.replace(",", ".", regex=False).str.strip())
    s = s.replace({"": "0", "nan": "0", "None": "0", "-": "0"})
    return pd.to_numeric(s, errors="coerce").fillna(0)


def clean_id(series: pd.Series) -> pd.Series:
    def _fix(v):
        s = str(v).strip()
        if s in ("", "nan", "None", "NaT"):
            return "0"
        if s.lstrip("-").isdigit():
            return s
        if "." in s or "e" in s.lower():
            try:
                f = float(s)
                if f.is_integer():
                    return str(int(f))
            except (ValueError, TypeError):
                pass
        return s
    return series.apply(_fix)


def categorize(x):
    return "Излишки" if x < 0 else "Недостачи" if x > 0 else "Без расхождений"


def finalize(raw: pd.DataFrame) -> pd.DataFrame:
    d = normalize_columns(raw)
    for c in NUMERIC_COLS:
        d[c] = clean_numeric(d[c])
    for c in ["sku", "magnit_code"]:
        d[c] = clean_id(d[c])
    d["description"] = d["description"].fillna("0").astype(str).str.strip()
    d.loc[d["description"].isin(["", "nan", "None"]), "description"] = "0"
    for c in NUMERIC_COLS:
        d[c] = d[c].round(0).astype("int64")
    d = d.groupby(GROUP_COLS, as_index=False)[NUMERIC_COLS].sum()
    d["category"] = d["discrepancy"].apply(categorize)
    return d.reset_index(drop=True)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def load_from_sheet():
    debug = {"url": SHEET_URL}
    try:
        resp = requests.get(SHEET_URL, timeout=12)
        debug["status_code"] = resp.status_code
        resp.raise_for_status()
        resp.encoding = "utf-8"
        text = resp.text
        debug["response_length"] = len(text)
        if text.strip().lower().startswith("<!doctype") or "<html" in text[:200].lower():
            debug["error"] = "Ответ похож на HTML-страницу (нет доступа), а не на CSV"
            raise ValueError("no access")
        raw = pd.read_csv(io.StringIO(text), dtype=str)
        debug["raw_columns"] = list(raw.columns)
        debug["raw_row_count"] = len(raw)
        final = finalize(raw)
        debug["final_row_count"] = len(final)
        return final, True, debug
    except Exception as e:
        debug["exception"] = f"{type(e).__name__}: {e}"
        return finalize(pd.read_csv(io.StringIO(SAMPLE_DATA_CSV), dtype=str)), False, debug


def norm_type(t) -> str:
    t = " ".join(str(t).replace("\n", " ").split()).lower()
    t = t.replace("передпросрок", "предпросрок")
    if t.startswith("излишка с инвент"):
        t = "излишка с инвентаризации"
    return t[:1].upper() + t[1:]


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def load_okk():
    """Читает вкладки с «Тип расхождения» и «Разница». Возвращает (df, debug)."""
    frames, debug = [], {}
    for tab, gid in OKK_TABS.items():
        if not gid:
            debug[tab] = "gid не указан — вкладка пропущена"
            continue
        try:
            url = f"https://docs.google.com/spreadsheets/d/{OKK_SHEET_ID}/export?format=csv&gid={gid}"
            r = requests.get(url, timeout=25)
            r.raise_for_status()
            r.encoding = "utf-8"
            raw = pd.read_csv(io.StringIO(r.text), dtype=str, header=None)
            hdr = next(i for i in range(min(len(raw), 40))
                       if raw.iloc[i].astype(str).str.lower().str.contains("тип расхожд").any())
            cols = [str(c).strip().lower() for c in raw.iloc[hdr]]
            body = raw.iloc[hdr + 1:]

            def pick(*keys):
                return [i for i, c in enumerate(cols) if any(k in c for k in keys)]

            def one(*keys):
                ix = pick(*keys)
                return body.iloc[:, ix[0]] if ix else pd.Series("", index=body.index)

            com = body.iloc[:, pick("комментар", "куда израсход")].fillna("").astype(str) \
                if pick("комментар", "куда израсход") else pd.DataFrame({"c": [""] * len(body)}, index=body.index)
            comment = com.apply(lambda row: " | ".join(v.strip() for v in row if v.strip() and v != "nan"), axis=1)
            part = pd.DataFrame({
                "Строка": body.index + 1, "Источник": tab,
                "№ накладной": one("накладн").fillna("").astype(str).str.strip(),
                "Дата": one("дата").fillna("").astype(str),
                "ШК": clean_id(one("шк").fillna("")),
                "Наименование": one("наименование").fillna("").astype(str).str.strip(),
                "Тип расхождения": one("тип расхожд").fillna("").astype(str).map(norm_type),
                "Кол-во": clean_numeric(one("разница")).round(0).astype("int64"),
                "Комментарий": comment,
            })
            part = part[~part["Тип расхождения"].isin(["", "Nan"])]
            frames.append(part)
            debug[tab] = f"ok, строк: {len(part)}"
        except Exception as e:
            debug[tab] = f"{type(e).__name__}: {e}"
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=OKK_COLS)
    return out[OKK_COLS], debug


def okk_sheets(o: pd.DataFrame) -> dict:
    summ = (o.groupby("Тип расхождения", as_index=False)
            .agg(**{"Строк": ("Строка", "count"), "Кол-во": ("Кол-во", "sum")})
            .sort_values("Строк", ascending=False))
    return {"ОКК": o[OKK_EXPORT], "ОКК итоги": summ}


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def okk_bytes(o: pd.DataFrame, tname: str | None = None) -> bytes:
    d = o if tname is None else o[o["Тип расхождения"] == tname]
    return to_excel_bytes({}, extra_sheets={(tname or "Все типы")[:31]: d[OKK_EXPORT]})


# ───────────────────────────── EXCEL ─────────────────────────────
def to_excel_bytes(sheets: dict, drop_cols: dict | None = None, extra_sheets: dict | None = None) -> bytes:
    drop_cols = drop_cols or {}
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        wb = writer.book
        header_fmt = wb.add_format({"bold": True, "bg_color": "#20242f", "font_color": "white",
                                    "border": 1, "align": "center", "valign": "vcenter"})
        pos_fmt = wb.add_format({"font_color": "#B91C1C"})
        neg_fmt = wb.add_format({"font_color": "#15803D"})
        text_fmt = wb.add_format({"num_format": "@"})
        id_cols = {DISPLAY_NAMES["sku"], DISPLAY_NAMES["magnit_code"]}
        for sheet_name, data in sheets.items():
            data = data[data["description"] != "0"]
            data = data.reindex(data["discrepancy"].abs().sort_values(ascending=False).index)
            out = data.rename(columns=DISPLAY_NAMES).drop(columns=["category"], errors="ignore")
            for extra in drop_cols.get(sheet_name, []):
                out = out.drop(columns=[extra], errors="ignore")
            name = sheet_name[:31]
            out.to_excel(writer, sheet_name=name, index=False)
            ws = writer.sheets[name]
            for i, col in enumerate(out.columns):
                ws.write(0, i, col, header_fmt)
                if len(out):
                    ws.set_column(i, i, max(14, min(46, int(out[col].astype(str).str.len().max() or 14) + 2)))
                    if col in id_cols:
                        for r, val in enumerate(out[col].astype(str), start=1):
                            ws.write_string(r, i, val, text_fmt)
            if "Рассхождения" in out.columns and len(out):
                ci = list(out.columns).index("Рассхождения")
                ws.conditional_format(1, ci, len(out), ci, {"type": "cell", "criteria": "<", "value": 0, "format": neg_fmt})
                ws.conditional_format(1, ci, len(out), ci, {"type": "cell", "criteria": ">", "value": 0, "format": pos_fmt})
        for name, edf in (extra_sheets or {}).items():
            name = name[:31]
            edf.to_excel(writer, sheet_name=name, index=False)
            ws = writer.sheets[name]
            for i, col in enumerate(edf.columns):
                ws.write(0, i, col, header_fmt)
                ws.set_column(i, i, max(12, min(46, int(edf[col].astype(str).str.len().max() or 12) + 2)) if len(edf) else 14)
                if col == "ШК":
                    for r, v in enumerate(edf[col].astype(str), start=1):
                        ws.write_string(r, i, v, text_fmt)
    return output.getvalue()


def subset(data: pd.DataFrame, kind: str) -> pd.DataFrame:
    if kind == "excess":
        return data[data["discrepancy"] < 0]
    if kind == "shortage":
        return data[data["discrepancy"] > 0]
    if kind == "zero":
        return data[data["discrepancy"] == 0]
    if kind == "loss":
        return data[data["lost"] > 0]
    return data


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def export_bytes(kind: str, data: pd.DataFrame, okk: pd.DataFrame | None = None) -> bytes:
    """kind='full' — одна книга: лист «Все товары» + отдельные листы по категориям."""
    drop = {"Потери": [DISPLAY_NAMES["discrepancy"]]}
    if kind == "full":
        extra = okk_sheets(okk) if okk is not None and len(okk) else None   # ОКК — только в общей выгрузке
        return to_excel_bytes({v[5]: subset(data, k) for k, v in KINDS.items()}, drop_cols=drop, extra_sheets=extra)
    return to_excel_bytes({KINDS[kind][5]: subset(data, kind)}, drop_cols=drop)


def fallback_panel(files):
    """Резервная выгрузка через браузерный Blob — не зависит от медиа-сервера Streamlit."""
    payload = json.dumps([{"n": n, "l": l, "d": base64.b64encode(b).decode()} for l, n, b in files])
    components.html(f"""
<style>
button{{width:100%;margin:0 0 8px;padding:10px;border:0;border-radius:10px;cursor:pointer;font:700 13px Inter,sans-serif;
color:#fff;background:linear-gradient(90deg,#7C3AED,#0EA5E9)}}
button:hover{{filter:brightness(1.1)}}
</style><div id="r"></div>
<script>
const F={payload}, r=document.getElementById('r');
F.forEach(f=>{{const b=document.createElement('button');b.textContent='⬇ '+f.l;
b.onclick=()=>{{const s=atob(f.d),u=new Uint8Array(s.length);for(let i=0;i<s.length;i++)u[i]=s.charCodeAt(i);
const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([u],{{type:'{XLSX_MIME}'}}));
a.download=f.n;document.body.appendChild(a);a.click();a.remove();}};r.appendChild(b);}});
</script>""", height=50 * len(files) + 10)


# ───────────────────────────── ДАННЫЕ ─────────────────────────────
with st.spinner("⏳ Загружаю данные из Google Таблицы…"):
    df, is_live, debug_info = load_from_sheet()
    okk_df, okk_debug = load_okk()
TS = datetime.now().strftime("%Y%m%d_%H%M")


def fmt(n):
    return f"{n:,}".replace(",", " ")


total = len(df)
excess_n = int((df["discrepancy"] < 0).sum())
shortage_n = int((df["discrepancy"] > 0).sum())
zero_n = total - excess_n - shortage_n
loss_n = int((df["lost"] > 0).sum())
qty_excess = abs(int(df.loc[df["discrepancy"] < 0, "discrepancy"].sum()))
qty_shortage = int(df.loc[df["discrepancy"] > 0, "discrepancy"].sum())
qty_lost = int(df["lost"].sum())
qty_total = int(df["stock"].sum())
qty_zero = int(df.loc[df["category"] == "Без расхождений", "stock"].sum())


def pct(n):
    return n / total * 100 if total else 0


# ───────────────────────────── SIDEBAR ─────────────────────────────
with st.sidebar:
    st.markdown("### 🔍 Поиск")
    search = st.text_input("Поиск", placeholder="СКЮ, код Магнита или название…", label_visibility="collapsed")
    st.markdown("### 🛟 Резервная выгрузка")
    st.caption("Если обычные кнопки не скачивают файл — включите, появятся запасные кнопки.")
    if st.toggle("Показать запасные кнопки"):
        fallback_panel([("Все товары (книга)", f"vse_tovary_{TS}.xlsx", export_bytes("full", df, okk_df))] +
                       [(KINDS[k][0], f"{KINDS[k][1]}_{TS}.xlsx", export_bytes(k, df)) for k in KINDS if k != "all"])
    with st.expander("🔧 Диагностика загрузки", expanded=not is_live):
        st.json(debug_info)
        st.json({"ОКК": okk_debug})
    st.caption(f"Streamlit {st.__version__}")

# ───────────────────────────── HERO ─────────────────────────────
if "filter_mode" not in st.session_state:
    st.session_state.filter_mode = "all"

h1, h2 = st.columns([4, 1.1])
with h1:
    status = "Данные из Google Таблицы" if is_live else "Демо-данные (таблица недоступна)"
    st.markdown(f"""
<div class="hero">
<div>
<span class="badge"><span class="dot {'' if is_live else 'off'}"></span>{status}</span>
<h1>📦 Аналитика расхождений СКЮ</h1>
<p>Принято → Отгружено → Сток → Потери → Расхождения</p>
</div>
<div class="hero-stats">
<div><b>{fmt(total)}</b><span>СКЮ</span></div>
<div><b>{fmt(qty_total)}</b><span>шт на стоке</span></div>
<div><b>{datetime.now().strftime('%H:%M')}</b><span>обновлено</span></div>
</div>
</div>
""", unsafe_allow_html=True)
with h2:
    if st.button("🔄 Обновить данные", width="stretch"):
        st.cache_data.clear()
        st.rerun()
    with st.container(key="full_dl"):
        st.download_button("📥 Выгрузить ВСЕ товары", data=export_bytes("full", df, okk_df),
                           file_name=f"vse_tovary_{TS}.xlsx", mime=XLSX_MIME, key="dl_full", width="stretch")

# ───────────────────────────── KPI-КАРТОЧКИ ─────────────────────────────
st.markdown('<div class="sec">📈 Ключевые показатели <small>кнопка на карточке скачивает Excel с этой выборкой</small></div>',
            unsafe_allow_html=True)
cards = [
    ("all", fmt(qty_total), f"{fmt(total)} СКЮ · 100%", 100),
    ("excess", fmt(qty_excess), f"{pct(excess_n):.1f}% · {fmt(excess_n)} СКЮ", pct(excess_n)),
    ("shortage", fmt(qty_shortage), f"{pct(shortage_n):.1f}% · {fmt(shortage_n)} СКЮ", pct(shortage_n)),
    ("zero", fmt(qty_zero), f"{pct(zero_n):.1f}% · {fmt(zero_n)} СКЮ", pct(zero_n)),
    ("loss", fmt(qty_lost), f"{pct(loss_n):.1f}% · {fmt(loss_n)} СКЮ", pct(loss_n)),
]
for col, (kind, value, sub, p) in zip(st.columns(5), cards):
    with col:
        with st.container(key=f"card_{kind}"):
            st.markdown(f"""
<div class="k-top"><span class="k-ico">{KINDS[kind][2]}</span><span class="k-label">{KINDS[kind][0]}</span></div>
<div class="k-val">{value}<small> шт</small></div>
<div class="k-sub">{sub}</div>
<div class="k-bar"><i style="width:{p:.1f}%"></i></div>
""", unsafe_allow_html=True)
            st.download_button("⬇ Скачать Excel", data=export_bytes(kind, df),
                               file_name=f"{KINDS[kind][1]}_{TS}.xlsx", mime=XLSX_MIME,
                               key=f"dl_{kind}", width="stretch")

# ───────────────────────────── ГРАФИКИ ─────────────────────────────
st.markdown('<div class="sec">📊 Аналитика</div>', unsafe_allow_html=True)
g1, g2 = st.columns([1, 1.3])
with g1:
    donut = pd.DataFrame({"Категория": ["Излишки", "Недостачи", "Без расхождений"],
                          "Шт": [qty_excess, qty_shortage, qty_zero]})
    fig = px.pie(donut, names="Категория", values="Шт", hole=0.64, color="Категория",
                 color_discrete_map={"Излишки": "#16A34A", "Недостачи": "#DC2626", "Без расхождений": "#0891B2"})
    fig.update_traces(textposition="outside", textinfo="percent+label",
                      marker=dict(line=dict(color="#fff", width=3)), pull=[0.03, 0.03, 0])
    fig.add_annotation(text=f"<b>{fmt(int(donut['Шт'].sum()))}</b><br>шт", x=.5, y=.5, showarrow=False,
                       font=dict(size=20, color="#1E1B33"))
    fig.update_layout(showlegend=False, paper_bgcolor="rgba(0,0,0,0)", margin=dict(t=30, b=20, l=40, r=40),
                      height=380, title=dict(text="Структура по штукам", font=dict(size=15)))
    st.plotly_chart(fig, width="stretch")
with g2:
    top = df.assign(a=df["discrepancy"].abs()).nlargest(10, "a").copy()
    top["Позиция"] = top["description"].str.slice(0, 36)
    top["Тип"] = top["discrepancy"].gt(0).map({True: "Недостача", False: "Излишек"})
    fig2 = px.bar(top, x="discrepancy", y="Позиция", orientation="h", color="Тип",
                  color_discrete_map={"Недостача": "#DC2626", "Излишек": "#16A34A"},
                  labels={"discrepancy": "Расхождение, шт"})
    fig2.update_layout(yaxis=dict(autorange="reversed", title=None), paper_bgcolor="rgba(0,0,0,0)",
                       plot_bgcolor="rgba(0,0,0,0)", height=380, margin=dict(t=30, b=20, l=10, r=10),
                       legend=dict(orientation="h", y=-0.15, title=None),
                       title=dict(text="Топ-10 СКЮ по размеру расхождения", font=dict(size=15)))
    fig2.update_traces(marker_cornerradius=6)
    st.plotly_chart(fig2, width="stretch")

# ───────────────────────────── ТАБЛИЦА ─────────────────────────────
mode_titles = {"all": "Все позиции", "excess": "Излишки (расхождение «−»)",
               "shortage": "Недостачи (расхождение «+»)", "loss": "Позиции с потерями"}
labels = [("all", "📊 Все позиции"), ("excess", "📈 Излишки"), ("shortage", "📉 Недостачи"), ("loss", "⚠️ С потерями")]
st.markdown('<div class="sec">📋 Детализация по СКЮ</div>', unsafe_allow_html=True)
for i, (key, label) in enumerate(labels):
    kind = "primary" if st.session_state.filter_mode == key else "secondary"
    if st.columns(4)[i].button(label, width="stretch", type=kind, key=f"btn_{key}"):
        st.session_state.filter_mode = key
mode = st.session_state.filter_mode

filtered = df.copy()
if mode == "excess":
    filtered = filtered[filtered["discrepancy"] < 0]
elif mode == "shortage":
    filtered = filtered[filtered["discrepancy"] > 0]
elif mode == "loss":
    filtered = filtered[filtered["lost"] > 0]
if search:
    s = search.strip().lower()
    filtered = filtered[filtered["sku"].str.lower().str.contains(s, na=False)
                        | filtered["magnit_code"].str.lower().str.contains(s, na=False)
                        | filtered["description"].str.lower().str.contains(s, na=False)]
filtered = filtered.reindex(filtered["discrepancy"].abs().sort_values(ascending=False).index)

ex_f = abs(int(filtered.loc[filtered["discrepancy"] < 0, "discrepancy"].sum()))
sh_f = int(filtered.loc[filtered["discrepancy"] > 0, "discrepancy"].sum())
lost_f = int(filtered["lost"].sum())
st.markdown(f"""
<div class="sec" style="margin-top:14px">{mode_titles[mode]}<small>найдено {fmt(len(filtered))}</small></div>
<div class="strip">
<div>Потеряно: <b>{fmt(lost_f)}</b> шт</div>
<div>Сумма расхождений: <b>{fmt(int(filtered['discrepancy'].sum()))}</b> шт</div>
<div>Излишки + Недостачи + Потери: <b>{fmt(ex_f + sh_f + lost_f)}</b> шт</div>
</div>
""", unsafe_allow_html=True)

shown = filtered.rename(columns=DISPLAY_NAMES).drop(columns=["category"], errors="ignore")


def highlight_disc(v):
    if isinstance(v, (int, float)):
        if v < 0:
            return "color:#16A34A; font-weight:700;"
        if v > 0:
            return "color:#DC2626; font-weight:700;"
    return ""


styler = shown.style
try:
    styled = styler.map(highlight_disc, subset=["Рассхождения"])
except AttributeError:
    styled = styler.applymap(highlight_disc, subset=["Рассхождения"])
st.dataframe(styled, width="stretch", height=440, hide_index=True)

with st.container(key="filter_dl"):
    st.download_button(f"⬇️ Скачать текущую выборку ({fmt(len(filtered))} СКЮ)",
                       data=to_excel_bytes({mode_titles[mode][:31]: filtered}),
                       file_name=f"poisk_{mode}_{TS}.xlsx", mime=XLSX_MIME, key="dl_filter", width="stretch")

# ───────────── ОКК: типы расхождений (отдельный источник) ─────────────
st.markdown('<div class="sec">🧾 ОКК · Типы расхождений <small>отдельный источник — таблица «ФМСЖ Магнит Проблемные»; '
            'в общую выгрузку попадает листами «ОКК» и «ОКК итоги»</small></div>', unsafe_allow_html=True)
if okk_df.empty:
    st.warning("Данные по типам расхождений не загружены — см. боковую панель → «Диагностика загрузки». "
               "Проверьте, что таблица открыта по ссылке (доступ «Читатель»).")
else:
    if any(not g for g in OKK_TABS.values()):
        st.caption("ℹ️ Вкладка «Местн. поставщик» не подключена: укажите её gid в OKK_TABS в начале файла.")
    PAL = [("#6366F1", "#A78BFA"), ("#16A34A", "#4ADE80"), ("#DC2626", "#FB7185"), ("#0891B2", "#22D3EE"),
           ("#D97706", "#FBBF24"), ("#DB2777", "#F472B6"), ("#7C3AED", "#C084FC"), ("#0D9488", "#5EEAD4"),
           ("#EA580C", "#FDBA74")]
    agg = (okk_df.groupby("Тип расхождения", as_index=False)
           .agg(Строк=("Строка", "count"), Кол=("Кол-во", "sum")).sort_values("Строк", ascending=False))
    items = [("Все типы", len(okk_df), int(okk_df["Кол-во"].sum()), None)] + [
        (r["Тип расхождения"], int(r["Строк"]), int(r["Кол"]), r["Тип расхождения"]) for _, r in agg.iterrows()]
    st.markdown("<style>" + "".join(f".st-key-card_ok{i}{{--c:{PAL[i % 9][0]};--c2:{PAL[i % 9][1]};}}"
                                    for i in range(len(items))) + "</style>", unsafe_allow_html=True)
    for start in range(0, len(items), 4):
        for col, (i, (label, n, q, tname)) in zip(st.columns(4), list(enumerate(items))[start:start + 4]):
            share = n / len(okk_df) * 100
            with col:
                with st.container(key=f"card_ok{i}"):
                    st.markdown(f"""
<div class="k-top"><span class="k-ico">🧾</span><span class="k-label">{label}</span></div>
<div class="k-val">{fmt(q)}<small> шт</small></div>
<div class="k-sub">{fmt(n)} строк · {share:.1f}%</div>
<div class="k-bar"><i style="width:{share:.1f}%"></i></div>
""", unsafe_allow_html=True)
                    st.download_button("⬇ Скачать Excel", data=okk_bytes(okk_df, tname),
                                       file_name=f"okk_{i}_{TS}.xlsx", mime=XLSX_MIME, key=f"dl_ok{i}", width="stretch")

    fig3 = px.bar(agg, x="Кол", y="Тип расхождения", orientation="h", text_auto=True, color="Тип расхождения",
                  color_discrete_sequence=[c[0] for c in PAL[1:]], labels={"Кол": "Кол-во (Разница), шт"})
    fig3.update_layout(showlegend=False, yaxis=dict(autorange="reversed", title=None), paper_bgcolor="rgba(0,0,0,0)",
                       plot_bgcolor="rgba(0,0,0,0)", height=360, margin=dict(t=30, b=20, l=10, r=10),
                       title=dict(text="Количество по типам расхождения", font=dict(size=15)))
    fig3.update_traces(marker_cornerradius=6)
    st.plotly_chart(fig3, width="stretch")

    sel = st.multiselect("Тип расхождения", sorted(okk_df["Тип расхождения"].unique()), placeholder="Все типы")
    o = okk_df[okk_df["Тип расхождения"].isin(sel)] if sel else okk_df
    if search:
        q_ = search.strip().lower()
        o = o[o[["ШК", "Наименование", "№ накладной"]].astype(str)
              .apply(lambda c: c.str.lower().str.contains(q_, na=False)).any(axis=1)]
    st.markdown(f"""
<div class="strip">
<div>Строк: <b>{fmt(len(o))}</b></div>
<div>Кол-во (сумма «Разница»): <b>{fmt(int(o['Кол-во'].sum()))}</b> шт</div>
</div>
""", unsafe_allow_html=True)
    st.dataframe(o, width="stretch", height=400, hide_index=True)
    with st.container(key="filter_dl_okk"):
        st.download_button(f"⬇️ Скачать текущую выборку ОКК ({fmt(len(o))} строк)",
                           data=to_excel_bytes({}, extra_sheets={"ОКК": o[OKK_EXPORT]}),
                           file_name=f"okk_vyborka_{TS}.xlsx", mime=XLSX_MIME, key="dl_okk_filter", width="stretch")

st.markdown('<div style="text-align:center;color:#7C7A9E;margin-top:30px;font-size:12px;">'
            'Данные обновляются из Google Таблицы каждые 5 минут</div>', unsafe_allow_html=True)
