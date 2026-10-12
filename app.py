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
CODE_GID = ""   # ← gid вкладки «Код товара» (SKU WMS ID, barcode): сопоставление по ШК точнее, чем по названию
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

st.set_page_config(page_title="Аналитика расхождений СКЮ", page_icon="📦",
                   layout="wide", initial_sidebar_state="collapsed")

INTERNAL_COLS = ["sku", "magnit_code", "description", "received", "shipped", "stock", "lost", "discrepancy"]
DISPLAY_NAMES = {"sku": "СКЮ", "magnit_code": "Код Магнита", "description": "Описания",
                 "received": "Принято", "shipped": "Отгруженно", "stock": "Сток",
                 "lost": "Потеряно", "discrepancy": "Рассхождения",
                 "okk_qty": "ОКК", "okk_comment": "Комментарии ОКК"}
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
    "all":      ("Всего СКЮ",       "vse_tovary",       "📦", "#757575", "#A0A0A0", "Все товары"),
    "excess":   ("Излишки",         "izlishki",         "📈", "#6F6F6F", "#A7A7A7", "Излишки"),
    "shortage": ("Недостачи",       "nedostachi",       "📉", "#5C5C5C", "#9D9D9D", "Недостачи"),
    "zero":     ("Без расхождений", "bez_rashozhdeniy", "✅", "#6C6C6C", "#A1A1A1", "Без расхождений"),
    "loss":     ("С потерями",      "poteri",           "⚠️", "#878787", "#BFBFBF", "Потери"),
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
background: radial-gradient(700px 450px at 12% 8%, rgba(124,124,124,.24), transparent 70%),
            radial-gradient(650px 420px at 90% 6%, rgba(161,161,161,.22), transparent 70%),
            radial-gradient(700px 450px at 60% 100%, rgba(161,161,161,.18), transparent 70%),
            #F6F6F6 !important;
background-attachment: fixed !important;
}
@keyframes fadeUp { from { opacity:0; transform: translateY(16px); } to { opacity:1; transform:none; } }
@keyframes flow { to { background-position: 300% 0; } }
@keyframes pulse { 0%,100% { box-shadow: 0 0 0 0 rgba(167,167,167,.7); } 50% { box-shadow: 0 0 0 8px rgba(167,167,167,0); } }
@keyframes grow { from { width: 0; } }
.block-container { padding-top: 2rem; max-width: 1400px; }
h1, h2, h3, h4, p, span, label { color: #1F1F1F; }
footer { visibility: hidden; }

/* HERO */
.hero {
display: flex; justify-content: space-between; align-items: center; gap: 24px; flex-wrap: wrap;
padding: 30px 36px; border-radius: 24px; color: #fff;
background: linear-gradient(120deg, #383838, #515151, #808080, #515151, #383838);
background-size: 300% 100%; animation: flow 14s linear infinite, fadeUp .6s ease;
box-shadow: 0 20px 50px rgba(91,91,91,.35);
}
.hero h1 { color: #fff; font-size: 32px; font-weight: 900; margin: 10px 0 4px; letter-spacing: -.5px; }
.hero p { color: #E8E8E8; margin: 0; font-size: 14px; }
.badge { display: inline-flex; align-items: center; gap: 8px; padding: 5px 14px; border-radius: 999px;
background: rgba(255,255,255,.16); border: 1px solid rgba(255,255,255,.3); font-size: 12px; font-weight: 700; color: #fff; }
.dot { width: 9px; height: 9px; border-radius: 50%; background: #A7A7A7; animation: pulse 1.8s infinite; }
.dot.off { background: #BFBFBF; animation: none; }
.hero-stats { display: flex; gap: 14px; }
.hero-stats div { padding: 12px 20px; border-radius: 16px; text-align: center;
background: rgba(255,255,255,.14); border: 1px solid rgba(255,255,255,.25); backdrop-filter: blur(8px); }
.hero-stats b { display: block; font-size: 22px; font-weight: 900; color: #fff; }
.hero-stats span { font-size: 11px; color: #D4D4D4; text-transform: uppercase; letter-spacing: .6px; }

/* КАРТОЧКИ-ВЫГРУЗКИ: сама карточка = контейнер, кнопка скачивания внутри */
[class*="st-key-card_"] {
position: relative; overflow: hidden; gap: .55rem !important;
padding: 20px 20px 16px; border-radius: 22px;
background: rgba(255,255,255,.82); backdrop-filter: blur(14px);
border: 1px solid rgba(98,98,98,.10); box-shadow: 0 8px 28px rgba(91,91,91,.10);
transition: transform .25s ease, box-shadow .25s ease; animation: fadeUp .6s ease both;
}
[class*="st-key-card_"]::before { content: ""; position: absolute; left: 0; right: 0; top: 0; height: 5px;
background: linear-gradient(90deg, var(--c), var(--c2)); }
[class*="st-key-card_"]:hover { transform: translateY(-6px); box-shadow: 0 22px 44px rgba(91,91,91,.22); }
.k-top { display: flex; align-items: center; gap: 10px; min-height: 46px; }
.k-ico { width: 38px; height: 38px; border-radius: 12px; display: grid; place-items: center; font-size: 18px;
background: linear-gradient(135deg, var(--c), var(--c2)); box-shadow: 0 6px 14px rgba(0,0,0,.15); }
.k-label { line-height: 1.25; font-size: 12px; font-weight: 800; text-transform: uppercase; letter-spacing: .7px; color: #6C6C6C; }
.k-val { font-size: 32px; font-weight: 900; line-height: 1.1; margin-top: 4px;
background: linear-gradient(90deg, #111827, #4B5563); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.k-val small { font-size: 14px; font-weight: 700; }
.k-sub { font-size: 12.5px; font-weight: 700; color: #4B5563; }
.k-bar { height: 7px; border-radius: 99px; background: rgba(105,105,105,.12); overflow: hidden; margin: 4px 0 2px; }
.k-bar i { display: block; height: 100%; border-radius: 99px; background: linear-gradient(90deg, var(--c), var(--c2)); animation: grow 1.1s cubic-bezier(.22,1,.36,1) both; }
[class*="st-key-card_"] [data-testid="stDownloadButton"] button,
[class*="st-key-card_"] .stDownloadButton button {
width: 100%; border: none !important; border-radius: 12px !important; font-weight: 800 !important; color: #fff !important;
background: linear-gradient(90deg, #1F2937, #4B5563) !important; transition: all .2s ease !important;
}
[class*="st-key-card_"] [data-testid="stDownloadButton"] button:hover,
[class*="st-key-card_"] .stDownloadButton button:hover { filter: brightness(1.1); transform: translateY(-2px); box-shadow: 0 8px 18px rgba(0,0,0,.2); }
[class*="st-key-card_"] [data-testid="stDownloadButton"] button *, [class*="st-key-card_"] .stDownloadButton button * { color: #fff !important; }

/* ОБЩИЕ КНОПКИ */
div.stButton > button { border-radius: 14px !important; font-weight: 800 !important; background: #fff !important;
color: #393939 !important; border: 1px solid rgba(98,98,98,.25) !important; transition: all .2s ease !important; padding: .55rem 1rem; }
div.stButton > button:hover { transform: translateY(-2px); border-color: #626262 !important; box-shadow: 0 8px 18px rgba(98,98,98,.25); }
div.stButton > button[kind="primary"] { background: linear-gradient(90deg, #626262, #808080) !important; color: #fff !important; border: none !important; }
div.stButton > button[kind="primary"] * { color: #fff !important; }
.st-key-full_dl [data-testid="stDownloadButton"] button, .st-key-full_dl .stDownloadButton button,
[class*="st-key-filter_dl"] [data-testid="stDownloadButton"] button, [class*="st-key-filter_dl"] .stDownloadButton button {
width: 100%; border: none !important; border-radius: 14px !important; font-weight: 900 !important; color: #fff !important;
background: linear-gradient(90deg, #A7A7A7, #777777, #828282) !important; padding: .7rem 1rem; box-shadow: 0 10px 24px rgba(119,119,119,.35);
}
[class*="st-key-filter_dl"] [data-testid="stDownloadButton"] button, [class*="st-key-filter_dl"] .stDownloadButton button { background: linear-gradient(90deg, #626262, #808080) !important; box-shadow: 0 10px 24px rgba(91,91,91,.3); }
.st-key-full_dl button *, [class*="st-key-filter_dl"] button * { color: #fff !important; }

.sec { font-size: 20px; font-weight: 900; margin: 28px 0 10px; }
.sec small { font-size: 13px; font-weight: 600; color: #8D8D8D; margin-left: 8px; }
.panel { padding: 8px 12px; border-radius: 22px; background: rgba(255,255,255,.82); border: 1px solid rgba(98,98,98,.10); box-shadow: 0 8px 28px rgba(91,91,91,.08); }
.strip { display: flex; gap: 14px; flex-wrap: wrap; margin: 6px 0 14px; }
.strip div { padding: 10px 18px; border-radius: 14px; background: rgba(255,255,255,.85); border: 1px solid rgba(98,98,98,.14);
font-size: 13.5px; color: #464646; }
.strip b { color: #1F1F1F; font-size: 15px; }
span[data-baseweb="tag"] { background: #4B5563 !important; color: #fff !important; }
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


def norm_name(x) -> str:
    return " ".join(str(x).lower().replace("ё", "е").split())


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def load_codes() -> pd.DataFrame:
    """Вкладка «Код товара»: SKU WMS ID ↔ barcode (GTIN-14). Необязательна."""
    empty = pd.DataFrame(columns=["sku", "bc"])
    if not CODE_GID:
        return empty
    try:
        r = requests.get(f"https://docs.google.com/spreadsheets/d/{OKK_SHEET_ID}/export?format=csv&gid={CODE_GID}", timeout=25)
        r.raise_for_status()
        r.encoding = "utf-8"
        raw = pd.read_csv(io.StringIO(r.text), dtype=str)
        sc = next(c for c in raw.columns if "sku" in str(c).lower())
        bc = next(c for c in raw.columns if "barcode" in str(c).lower() or "штрих" in str(c).lower())
        d = pd.DataFrame({"sku": clean_id(raw[sc].fillna("")),
                          "bc": raw[bc].fillna("").astype(str).str.strip().str.replace(r"\.0$", "", regex=True)})
        return d[(d["sku"] != "") & (d["bc"] != "")].drop_duplicates("bc")
    except Exception:
        return empty


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def okk_match(okk: pd.DataFrame, data: pd.DataFrame) -> pd.DataFrame:
    """Добавляет колонку «СКЮ»: сначала по ШК (в т.ч. GTIN-14), затем по названию."""
    o = okk.copy()
    o["СКЮ"] = ""
    codes = load_codes()
    if len(codes):
        full = dict(zip(codes["bc"], codes["sku"]))
        g14 = {b[1:13]: sk for b, sk in zip(codes["bc"], codes["sku"]) if len(b) == 14}
        o["СКЮ"] = [full.get(b) or (g14.get(b[:12]) if len(b) == 13 else None) or "" for b in o["ШК"]]
    d = data.sort_values("stock", ascending=False).drop_duplicates("description")
    byname = dict(zip(d["description"].map(norm_name), d["sku"]))
    miss = o["СКЮ"] == ""
    o.loc[miss, "СКЮ"] = o.loc[miss, "Наименование"].map(norm_name).map(byname).fillna("")
    return o


def okk_agg(om: pd.DataFrame) -> pd.DataFrame:
    """По каждому СКЮ: сумма «Кол-во» и текст комментариев (типы + пометки)."""
    rows = []
    for sku, g in om[om["СКЮ"] != ""].groupby("СКЮ"):
        by_t = g.groupby("Тип расхождения")["Кол-во"].sum()
        txt = "; ".join(f"{t}: {int(q)}" for t, q in by_t.items())
        extra = "; ".join(dict.fromkeys(c for c in g["Комментарий"] if c))[:300]
        rows.append({"sku": sku, "okk_qty": int(g["Кол-во"].sum()), "okk_comment": txt + (" | " + extra if extra else "")})
    return pd.DataFrame(rows, columns=["sku", "okk_qty", "okk_comment"])


def with_okk(data: pd.DataFrame, okk) -> pd.DataFrame:
    if okk is None or okk.empty:
        return data
    out = data.merge(okk_agg(okk_match(okk, data)), on="sku", how="left")
    out["okk_qty"] = out["okk_qty"].astype("Int64")
    return out


def okk_sheets(o: pd.DataFrame) -> dict:
    summ = (o.groupby("Тип расхождения", as_index=False)
            .agg(**{"Строк": ("Строка", "count"), "Кол-во": ("Кол-во", "sum")})
            .sort_values("Строк", ascending=False))
    cols = OKK_EXPORT[:1] + ["СКЮ"] + OKK_EXPORT[1:] if "СКЮ" in o.columns else OKK_EXPORT
    return {"ОКК": o[cols], "ОКК итоги": summ}


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
        header_fmt = wb.add_format({"bold": True, "bg_color": "#242424", "font_color": "white",
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
        extra = okk_sheets(okk_match(okk, data)) if okk is not None and len(okk) else None
        sheets = {v[5]: subset(data, k) for k, v in KINDS.items()}
        sheets[KINDS["all"][5]] = with_okk(data, okk)       # ОКК-колонки только в «Все товары»
        return to_excel_bytes(sheets, drop_cols=drop, extra_sheets=extra)
    part = subset(data, kind)
    if kind == "all":
        part = with_okk(part, okk)
    return to_excel_bytes({KINDS[kind][5]: part}, drop_cols=drop)


def fallback_panel(files):
    """Резервная выгрузка через браузерный Blob — не зависит от медиа-сервера Streamlit."""
    payload = json.dumps([{"n": n, "l": l, "d": base64.b64encode(b).decode()} for l, n, b in files])
    components.html(f"""
<style>
button{{width:100%;margin:0 0 8px;padding:10px;border:0;border-radius:10px;cursor:pointer;font:700 13px Inter,sans-serif;
color:#fff;background:linear-gradient(90deg,#626262,#808080)}}
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
                       [(KINDS[k][0], f"{KINDS[k][1]}_{TS}.xlsx", export_bytes(k, df, okk_df)) for k in KINDS if k != "all"])
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
            st.download_button("⬇ Скачать Excel", data=export_bytes(kind, df, okk_df),
                               file_name=f"{KINDS[kind][1]}_{TS}.xlsx", mime=XLSX_MIME,
                               key=f"dl_{kind}", width="stretch")

# ───────────────────────────── ТАБЛИЦА ─────────────────────────────
mode_titles = {"all": "Все позиции", "excess": "Излишки (расхождение «−»)",
               "shortage": "Недостачи (расхождение «+»)", "loss": "Позиции с потерями"}
labels = [("all", "📊 Все позиции"), ("excess", "📈 Излишки"), ("shortage", "📉 Недостачи"), ("loss", "⚠️ С потерями")]
st.markdown('<div class="sec">📋 Детализация по СКЮ</div>', unsafe_allow_html=True)
fcols = st.columns(4)
for i, (key, label) in enumerate(labels):
    kind = "primary" if st.session_state.filter_mode == key else "secondary"
    if fcols[i].button(label, width="stretch", type=kind, key=f"btn_{key}"):
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
            return "color:#727272; font-weight:700;"
        if v > 0:
            return "color:#181818; font-weight:700;"
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
    _om = okk_match(okk_df, df)
    st.caption(f"🔗 Сопоставлено со СКЮ: {int((_om['СКЮ'] != '').sum())} из {len(_om)} строк"
               + ("" if CODE_GID else " (по названию; для точности по ШК укажите CODE_GID — gid вкладки «Код товара»)"))
    PAL = [("#757575", "#A0A0A0"), ("#6F6F6F", "#A7A7A7"), ("#5C5C5C", "#9D9D9D"), ("#6C6C6C", "#A1A1A1"),
           ("#878787", "#BFBFBF"), ("#666666", "#A1A1A1"), ("#626262", "#A4A4A4"), ("#6A6A6A", "#BEBEBE"),
           ("#7B7B7B", "#C6C6C6")]
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

st.markdown('<div style="text-align:center;color:#7F7F7F;margin-top:30px;font-size:12px;">'
            'Данные обновляются из Google Таблицы каждые 5 минут</div>', unsafe_allow_html=True)
