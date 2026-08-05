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


SAMPLE_DATA_CSV = """СКЮ,Код Магнита,Баркод,Описания,Принято,Отгруженно,Сток,Потерянно,Рассхождения
1000000000000005264,1000585538,2010005855381,Пакет-майка M Cosmetic мал 36х60 УЗ,374750,270581,102600,1141,428
1000000000000020941,8000107234,4680825420175,LAF Набор заколок для волос №1 в асс УЗ,79763,801,78962,0,0
1000000000000008137,8000107235,4680825420168,LAF Крабик для волос Фигурный в асс УЗ,60013,4341,55499,0,173
1000000000000016630,8000107224,4680825420120,LAF Крабик для волос №1 13см в асс УЗ,59737,3492,55855,12,378
1000000000000024589,8000038157,2080000381574,LAF Массажер для мытья головы ПДЛ26 в асс(СИ):6/108,40068,2123,37936,0,9
1000000000000015409,8000107223,4680825420137,LAF Крабик для волос №2 13см в асс УЗ,38695,2195,36507,12,-19
1000000000000020459,8000107233,4680825420182,LAF Набор заколок для волос №2 в асс УЗ,36862,701,35641,2,518
1000000000000021110,8000010602,2080000106023,LAF Набор детских колец 3шт(СИ):6/480,35930,1324,33809,8,789
1000000000000026199,8000107238,4680825420199,LAF Набор резинка и заколка для волос №1 в асс УЗ,28982,700,28290,0,-8
1000000000000015278,1000580140,4650062126338,САМЫЙ СОК Крем для рук Пряный инжир 75мл УЗ,26717,68,26619,0,30
1000000000000019759,8000107237,4680825420236,LAF Ободок №1 в асс УЗ,24120,1238,22890,0,-8
1000000000000027153,1000533997,4680328026133,LAF Матирующие салфетки зеленые 50 шт (СИ):3/501,24042,2159,21829,108,-54
1000000000000011946,1000549839,2010005498397,Пакет п/э маленький M Cosmetic Розовый УЗ,22710,17769,4927,0,14
1000000000000026032,4000104300,2040001043000,LAF Резинки для волос 9 шт Ombre пружинки в асс (СИ):4/240,22598,317,22281,0,0
1000000000000012143,1000586990,3014260287047,GILLETTE 2 Станок для бритья одноразовый 1шт УЗ,21542,798,20632,33,79
1000000000000005986,4000104290,2040001042904,LAF Резинки-пружинки База (СИ):6/480,21485,1286,20202,0,-3
1000000000000015002,1000580139,4650062126321,САМЫЙ СОК Крем для рук Бархатный персик 75мл УЗ,20973,204,20620,0,149
1000000000000026801,8000074030,4680825418882,SADOER Маска для лица с Алоэ Вера 25г УЗ,20880,3345,17527,0,8
1000000000000007733,8000107202,4680825419889,GT Спонж для макияжа №1 УЗ,20400,2168,18224,0,8
1000000000000019294,8000107209,4680825419896,GT Спонж для макияжа №2 УЗ,20400,2289,18095,0,16
1000000000000026799,8000074026,4680825418868,SADOER Маска для лица с экстрактом оливы 25г УЗ,20160,3102,17055,0,3
1000000000000026802,8000074027,4680825418844,SADOER Маска для лица с экстрактом овса 25г УЗ,20160,3089,17067,0,4
1000000000000026786,8000074029,4680825418851,SADOER Маска для лица с гиалуроновой кислотой 25г УЗ,20160,7695,12447,0,18
1000000000000026789,8000074025,4680825418875,SADOER Маска для лица с экстрактом слизи улитки 25г УЗ,20160,7411,12729,4,16
1000000000000026795,8000074028,4680825418837,SADOER Маска для лица с жемчужным рисом 25г УЗ,20160,7365,12767,2,26
1000000000000006184,8000009806,2080000098069,LAF Набор зажимов 2шт Мрамор (СИ):4/240,18449,5712,12719,26,-8
1000000000000027216,1000426953,2010004269530,LAF Матирующие салфетки (СИ):10/1000,18000,2132,15866,0,2
1000000000000024370,4000104354,2040001043543,LAF Резинки д/волос 3 шт Золото/Серебро пружинки (СИ):6/600,17486,121,17355,20,-10
1000000000000021332,8000003226,2080000032261,LAF Набор пуховка велюровая д/пудры 2шт треугол (СИ):4/1000,17053,10563,7159,132,-801
1000000000000007258,8000009809,2080000098090,LAF Краб акриловый бабочка Мрамор (СИ):3/240,16732,2794,13929,8,1
1000000000000017154,8000107240,4680825420243,LAF Ободок №2 в асс УЗ,15794,844,14988,0,-38
1000000000000018631,4000104284,2040001042843,LAF Резинки для волос 3 шт Color (СИ):4/1200,15701,2230,11655,0,1816
1000000000000020119,8000033272,2080000332729,LAF Резинка для волос плюшевая в асс НГ(СИ):10/480,15565,3496,12072,0,-3
1000000000000021062,8000010608,2080000106085,LAF Расческа компактная с декором (СИ):4/120,15507,1156,14258,0,93
1000000000000026797,8000074031,4680825418912,SADOER Маска для лица с календулой 25г УЗ,15120,3099,12021,0,0
1000000000000026793,8000074032,4680825418899,SADOER Маска для лица с экстрактом зеленого чая 25г УЗ,15120,3265,11857,0,-2
1000000000000026800,8000074033,4680825418905,SADOER Маска для лица с рисовой эссенцией 25г УЗ,15120,7507,7604,0,9
1000000000000020335,8000010593,2080000105934,LAF Пусеты детские 3 пары(СИ):6/480,15090,784,13610,4,692
1000000000000024612,8000107232,4680825420144,LAF Крабик для волос №3 13см в асс УЗ,14803,2519,12284,0,0
1000000000000002840,1000580141,4650062126345,САМЫЙ СОК Крем для рук Солнечный гранат 75мл УЗ,14375,160,14096,0,119
1000000000000012851,1000054397,4607164997861,LA FRESH Зубочистки бамбуковые 280шт (СИ):12/600,14311,1113,12558,0,640
1000000000000007120,4000104355,2040001043550,LAF Набор резинок д/волос 4 шт текстиль в асс-те (СИ):6/600,14005,1467,12565,0,-27
1000000000000018754,4000104283,2040001042836,LAF Резинки для волос 6 шт пружинки дет (СИ):6/480,13981,336,13640,4,1
1000000000000012678,8000107239,4680825420229,LAF Набор заколок для волос №3 в асс УЗ,12401,163,12238,0,0
1000000000000026791,8000074034,4680825418929,MOXIE GIRLZ Маска для лица подтяг д/подбородка и щек 25г УЗ,12240,3895,8341,0,4
1000000000000027158,1000559990,4660476353879,ПН LAF Помада и карандаш д/губ прикасса (СИ):6/720,12240,2119,9555,0,566
1000000000000017769,1000586946,4780012871954,АЛЛОМА Тетрадь 12 листов в клетку УЗ,12229,6131,6109,10,-21
1000000000000005459,8000069635,4780030033785,SUNLIGHT Влажные салфетки Universal XXL 9шт УЗ,12144,14012,1186,171,-3225
1000000000000027157,1000559991,4660476353886,ПН LAF Масло для губ 2шт мини (СИ):4/144,12096,2181,9948,0,-33
1000000000000021504,1000235861,4604049095469,AOS Гель для мытья посуды Бальзам/Лимон Микс 450г(Нэфис):18,12000,8938,3012,32,18
1000000000000013177,4000072776,2040000727765,LAF Набор косметическ спонжей в короб 2шт в ассорт(СИ):3/600,11645,218,11430,0,-3
1000000000000027240,8000012168,4680328042294,LAF Полоски для носа 6шт в коробке (СИ): 12/144,11520,1109,10392,0,19
1000000000000001941,1000586947,4780012871947,АЛЛОМА Тетрадь 12 листов в линейку УЗ,10815,5215,5574,25,1
1000000000000005964,8000045854,4605922040330,ЧИСТАЯ ЛИНИЯ Сухой шампунь с экстрактом хлопка 200мл:6,10782,3808,6964,0,10
1000000000000021814,4000104306,2040001043062,LAF Резинка для волос 3 шт Беж в асс-те (СИ):4/480,10407,2217,8195,0,-5
1000000000000011248,1000586991,4780012871985,ALFA Тетрадь в клетку 48 листов УЗ,10302,1076,9302,32,-108
1000000000000022498,1000068360,2010000683606,LA FRESH Прокладки Comfort Soft 10шт(Хайджин):20,10200,5110,5085,14,-9
1000000000000018065,8000107229,4680825420151,LAF Крабик для волос №4 в асс УЗ,10027,694,9335,0,-2
1000000000000026796,8000127073,4680825414273,GT Пакет-шапочка для хранения и упаковки 100шт УЗ,9990,18,9972,0,0
1000000000000022173,4000104962,2040001049620,LAF Пемза для удаления кутикулы в ассорт(СИ):3/720,9897,919,8890,74,14
1000000000000019874,1000586724,4780105930049,AMELI Капсула для стирки 1шт УЗ,9720,9690,17,36,-23
1000000000000006335,1000195200,46034595,CHUPA CHUPS Кондит изд фрукт+кола 12г(Ван Мелле):100/1200,9605,9282,169,4,150
1000000000000001857,8000051717,2080000517171,LAF Резинка для волос Цветок СЛ в ассортименте (СИ):6/120,9292,464,8823,4,1
1000000000000008227,4000034766,2040000347666,LAF Точилка косметич д/каранд артPSP-003 в ассорт(СИ):3/360,9137,689,8424,0,24
1000000000000003735,4000094112,2040000941123,LAF Пилка маникюрная наждачная 180/220(СИ):6/288,8928,188,8740,0,0
1000000000000010781,8000015688,2080000156882,LAF Набор разноцв пилок для ногтей 200/240 5 шт (СИ):4/240,8640,2946,5681,40,-27
1000000000000005200,8000002452,2080000024525,LAF Beige Кисть для тональной основы и консилера (СИ):3/72,8569,388,8179,4,-2
1000000000000001789,1000580169,4650062122859,САМЫЙ СОК Гель для душа Витаминный коктейль Черника 200мл УЗ,8556,252,8300,0,4
1000000000000013768,8000002443,2080000024433,LAF Colour Кисть кабуки для пудры (СИ):4/96,8510,84,8426,0,0
1000000000000017678,8000112807,4814628011234,SUNDAY Стиральный порошок Автомат Универс Цветоч аром 5кг УЗ,8287,4730,3588,30,-61
1000000000000025545,8000009804,2080000098045,LAF Набор мини крабы 2шт Мрамор (СИ):4/240,8283,1614,6673,0,-4
1000000000000017688,4000094142,2040000941420,LAF Резинки для волос женские Вельвет 3 шт (СИ):3/240,8277,866,7410,0,1
1000000000000026173,8000107227,4680825420205,LAF Набор резинок для волос №1 2шт в асс УЗ,8230,279,7949,0,2
1000000000000001640,8000002431,2080000024310,LAF Спонж для макияжа в футляре 6шт треугольники (СИ):3/240,8158,18,8140,0,0
1000000000000006392,8000107230,4680825420212,LAF Набор резинка и заколка для волос №2 в асс УЗ,8088,177,7879,0,32
1000000000000018425,8000001315,2080000013154,LAF Набор резинок пружинок базовых 6 шт ШБ (СИ):12/480,8078,419,7671,0,-12
1000000000000004357,8000010388,2080000103886,LAF Краб для волос черный матовый База (СИ):3/240,8074,858,7216,0,0
1000000000000018627,8000002444,2080000024440,LAF Beige Кисть для пудры (СИ):4/72,8038,799,7242,0,-3
1000000000000020378,4000073386,2040000733865,LAF Заколки для волос жемчуг 2шт в асс(СИ):3/36,8028,648,7380,0,0
1000000000000006178,8000010416,2080000104166,LAF Краб для волос черный матовый большой База(СИ):3/240,8023,1006,7023,0,-6
1000000000000009771,8000010596,2080000105965,LAF Набор детских браслетов с декором 3шт(СИ):6/240,7842,854,6751,0,237
1000000000000007731,8000000951,2080000009515,LAF Крабы жемчужные мини в ШБ (СИ):10/160,7811,138,7675,0,-2
1000000000000008683,4000094125,2040000941253,LAF Набор маникюрный пилки 2шт в ассорт(СИ):6/216,7774,85,7689,0,0
1000000000000016679,1000570752,4780069000086,BONAQUA Вода питьевая с минералами н/газ 0.5л УЗ,7656,7148,504,0,4
1000000000000009694,4000094122,2040000941222,LAF Набор маникюрный мини ножницы/пилка алмазная(СИ):4/144,7654,406,7104,0,144
1000000000000002277,4000104317,2040001043178,LAF Резинки д/волос 3шт Жемчуг пружинка в асс-те(СИ):6/480,7652,35,7617,0,0
1000000000000013484,4000094121,2040000941215,LAF Книпсер маникюрный с пилкой(СИ):4/144,7625,363,7254,0,8
1000000000000023381,8000026108,2080000261081,LAF Ободок корона ДС5 (СИ):6/480,7618,180,7438,0,0
1000000000000004011,8000057559,2080000575591,LAF Набор резинок д/волос СЛ в асс-те (СИ):6/600,7523,693,6829,10,-9
1000000000000021685,1000582859,9000101830910,PERSIL Капсула для стирки Universal 1шт УЗ,7500,5592,900,60,948
1000000000000002742,4000094128,2040000941284,LAF Пемза для ног овальная (СИ):4/240,7456,1922,5531,0,3
1000000000000015198,1000187049,2010001870494,LA FRESH Ватные палочки 200шт п/уп (шнурок)(Белла): 48,7348,1811,5539,22,-24
1000000000000016966,4000104294,2040001042942,LAF Набор аксессуаров для волос 4 шт (СИ):4/480,7323,836,6494,0,-7
1000000000000015072,1000441981,4780030030760,SUNLIGHT Влажные салфетки карм Woman 2021 15х144 УЗ,7309,6980,326,210,-207
1000000000000012660,1000529247,3600524135157,LOREAL Elseve Шампунь д/вол гиалуон Pure 400мл:6,7300,3171,3554,1061,-486
1000000000000025235,8000048695,2080000486958,LAF Ободок детский ушки жемчуг перл ДС6 в асс (СИ):5/480,7229,786,5710,0,733
1000000000000025928,1000484216,4680328009891,LA FRESH Прокладки ежедневные гигиенические жен 20шт(СИ):36,7224,1307,5813,161,-57
1000000000000015108,8000010352,2080000103527,LAF Резинки д/волос 20шт тонкие черные(СИ):6/480,7200,598,6596,0,6
1000000000000010190,8000024698,2080000246989,LAF Набор резинок д/волос 2шт Бантики ДС5(СИ):6/480,7198,388,6810,0,0"""


@st.cache_data(show_spinner=False)
def load_sample() -> pd.DataFrame:
    raw = pd.read_csv(io.StringIO(SAMPLE_DATA_CSV))
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
