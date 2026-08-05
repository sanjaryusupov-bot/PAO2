"""
Дашборд «Аналитика расхождений СКЮ»
Источник данных — фиксированная Google Таблица (см. константы ниже).
"""

import io
from datetime import datetime

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

# ──────────────────────────────────────────────────────────────────────────
# КОНФИГУРАЦИЯ (поменять здесь, если понадобится другая таблица/лист)
# ──────────────────────────────────────────────────────────────────────────
SHEET_ID = "1xpiftC3wy1QRDdBxklSbgl5Ph4eW0wGcl8as9mIZXuU"
GID = "447006824"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"
CACHE_TTL_SECONDS = 300

st.set_page_config(
    page_title="Аналитика расхождений СКЮ",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

INTERNAL_COLS = [
    "sku", "magnit_code", "description",
    "received", "shipped", "stock", "lost", "discrepancy",
]
DISPLAY_NAMES = {
    "sku": "СКЮ",
    "magnit_code": "Код Магнита",
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
    "description": ["описани"],
    "received": ["принято"],
    "shipped": ["отгружен"],
    "stock": ["сток"],
    "lost": ["потер"],
    "discrepancy": ["рассхожд", "расхожд"],
}
NUMERIC_COLS = ["received", "shipped", "stock", "lost", "discrepancy"]
GROUP_COLS = ["sku", "magnit_code", "description"]

# ──────────────────────────────────────────────────────────────────────────
# ВСТРОЕННЫЕ ДЕМО-ДАННЫЕ (используются только если Google Таблица недоступна)
# ──────────────────────────────────────────────────────────────────────────
SAMPLE_DATA_CSV = """СКЮ,Код Магнита,Описания,Принято,Отгруженно,Сток,Потерянно,Рассхождения
1000000000000005264,1000585538,Пакет-майка M Cosmetic мал 36х60 УЗ,374750,270581,102600,1141,428
1000000000000020941,8000107234,LAF Набор заколок для волос №1 в асс УЗ,79763,801,78962,0,0
1000000000000008137,8000107235,LAF Крабик для волос Фигурный в асс УЗ,60013,4341,55499,0,173
1000000000000016630,8000107224,LAF Крабик для волос №1 13см в асс УЗ,59737,3492,55855,12,378
1000000000000024589,8000038157,LAF Массажер для мытья головы ПДЛ26 в асс(СИ):6/108,40068,2123,37936,0,9
1000000000000015409,8000107223,LAF Крабик для волос №2 13см в асс УЗ,38695,2195,36507,12,-19
1000000000000020459,8000107233,LAF Набор заколок для волос №2 в асс УЗ,36862,701,35641,2,518
1000000000000021110,8000010602,LAF Набор детских колец 3шт(СИ):6/480,35930,1324,33809,8,789
1000000000000026199,8000107238,LAF Набор резинка и заколка для волос №1 в асс УЗ,28982,700,28290,0,-8
1000000000000015278,1000580140,САМЫЙ СОК Крем для рук Пряный инжир 75мл УЗ,26717,68,26619,0,30
1000000000000019759,8000107237,LAF Ободок №1 в асс УЗ,24120,1238,22890,0,-8
1000000000000027153,1000533997,LAF Матирующие салфетки зеленые 50 шт (СИ):3/501,24042,2159,21829,108,-54
1000000000000011946,1000549839,Пакет п/э маленький M Cosmetic Розовый УЗ,22710,17769,4927,0,14
1000000000000026032,4000104300,LAF Резинки для волос 9 шт Ombre пружинки в асс (СИ):4/240,22598,317,22281,0,0
1000000000000012143,1000586990,GILLETTE 2 Станок для бритья одноразовый 1шт УЗ,21542,798,20632,33,79
1000000000000005986,4000104290,LAF Резинки-пружинки База (СИ):6/480,21485,1286,20202,0,-3
1000000000000015002,1000580139,САМЫЙ СОК Крем для рук Бархатный персик 75мл УЗ,20973,204,20620,0,149
1000000000000026801,8000074030,SADOER Маска для лица с Алоэ Вера 25г УЗ,20880,3345,17527,0,8
1000000000000007733,8000107202,GT Спонж для макияжа №1 УЗ,20400,2168,18224,0,8
1000000000000019294,8000107209,GT Спонж для макияжа №2 УЗ,20400,2289,18095,0,16
1000000000000026799,8000074026,SADOER Маска для лица с экстрактом оливы 25г УЗ,20160,3102,17055,0,3
1000000000000026802,8000074027,SADOER Маска для лица с экстрактом овса 25г УЗ,20160,3089,17067,0,4
1000000000000026786,8000074029,SADOER Маска для лица с гиалуроновой кислотой 25г УЗ,20160,7695,12447,0,18
1000000000000026789,8000074025,SADOER Маска для лица с экстрактом слизи улитки 25г УЗ,20160,7411,12729,4,16
1000000000000026795,8000074028,SADOER Маска для лица с жемчужным рисом 25г УЗ,20160,7365,12767,2,26
1000000000000006184,8000009806,LAF Набор зажимов 2шт Мрамор (СИ):4/240,18449,5712,12719,26,-8
1000000000000027216,1000426953,LAF Матирующие салфетки (СИ):10/1000,18000,2132,15866,0,2
1000000000000024370,4000104354,LAF Резинки д/волос 3 шт Золото/Серебро пружинки (СИ):6/600,17486,121,17355,20,-10
1000000000000021332,8000003226,LAF Набор пуховка велюровая д/пудры 2шт треугол (СИ):4/1000,17053,10563,7159,132,-801
1000000000000007258,8000009809,LAF Краб акриловый бабочка Мрамор (СИ):3/240,16732,2794,13929,8,1
1000000000000017154,8000107240,LAF Ободок №2 в асс УЗ,15794,844,14988,0,-38
1000000000000018631,4000104284,LAF Резинки для волос 3 шт Color (СИ):4/1200,15701,2230,11655,0,1816
1000000000000020119,8000033272,LAF Резинка для волос плюшевая в асс НГ(СИ):10/480,15565,3496,12072,0,-3
1000000000000021062,8000010608,LAF Расческа компактная с декором (СИ):4/120,15507,1156,14258,0,93
1000000000000026797,8000074031,SADOER Маска для лица с календулой 25г УЗ,15120,3099,12021,0,0
1000000000000026793,8000074032,SADOER Маска для лица с экстрактом зеленого чая 25г УЗ,15120,3265,11857,0,-2
1000000000000026800,8000074033,SADOER Маска для лица с рисовой эссенцией 25г УЗ,15120,7507,7604,0,9
1000000000000020335,8000010593,LAF Пусеты детские 3 пары(СИ):6/480,15090,784,13610,4,692
1000000000000024612,8000107232,LAF Крабик для волос №3 13см в асс УЗ,14803,2519,12284,0,0
1000000000000002840,1000580141,САМЫЙ СОК Крем для рук Солнечный гранат 75мл УЗ,14375,160,14096,0,119
1000000000000012851,1000054397,LA FRESH Зубочистки бамбуковые 280шт (СИ):12/600,14311,1113,12558,0,640
1000000000000007120,4000104355,LAF Набор резинок д/волос 4 шт текстиль в асс-те (СИ):6/600,14005,1467,12565,0,-27
1000000000000018754,4000104283,LAF Резинки для волос 6 шт пружинки дет (СИ):6/480,13981,336,13640,4,1
1000000000000012678,8000107239,LAF Набор заколок для волос №3 в асс УЗ,12401,163,12238,0,0
1000000000000026791,8000074034,MOXIE GIRLZ Маска для лица подтяг д/подбородка и щек 25г УЗ,12240,3895,8341,0,4
1000000000000027158,1000559990,ПН LAF Помада и карандаш д/губ прикасса (СИ):6/720,12240,2119,9555,0,566
1000000000000017769,1000586946,АЛЛОМА Тетрадь 12 листов в клетку УЗ,12229,6131,6109,10,-21
1000000000000005459,8000069635,SUNLIGHT Влажные салфетки Universal XXL 9шт УЗ,12144,14012,1186,171,-3225
1000000000000027157,1000559991,ПН LAF Масло для губ 2шт мини (СИ):4/144,12096,2181,9948,0,-33
1000000000000021504,1000235861,AOS Гель для мытья посуды Бальзам/Лимон Микс 450г(Нэфис):18,12000,8938,3012,32,18
1000000000000013177,4000072776,LAF Набор косметическ спонжей в короб 2шт в ассорт(СИ):3/600,11645,218,11430,0,-3
1000000000000027240,8000012168,LAF Полоски для носа 6шт в коробке (СИ): 12/144,11520,1109,10392,0,19
1000000000000001941,1000586947,АЛЛОМА Тетрадь 12 листов в линейку УЗ,10815,5215,5574,25,1
1000000000000005964,8000045854,ЧИСТАЯ ЛИНИЯ Сухой шампунь с экстрактом хлопка 200мл:6,10782,3808,6964,0,10
1000000000000021814,4000104306,LAF Резинка для волос 3 шт Беж в асс-те (СИ):4/480,10407,2217,8195,0,-5
1000000000000011248,1000586991,ALFA Тетрадь в клетку 48 листов УЗ,10302,1076,9302,32,-108
1000000000000022498,1000068360,LA FRESH Прокладки Comfort Soft 10шт(Хайджин):20,10200,5110,5085,14,-9
1000000000000018065,8000107229,LAF Крабик для волос №4 в асс УЗ,10027,694,9335,0,-2
1000000000000026796,8000127073,GT Пакет-шапочка для хранения и упаковки 100шт УЗ,9990,18,9972,0,0
1000000000000022173,4000104962,LAF Пемза для удаления кутикулы в ассорт(СИ):3/720,9897,919,8890,74,14
1000000000000019874,1000586724,AMELI Капсула для стирки 1шт УЗ,9720,9690,17,36,-23
1000000000000006335,1000195200,CHUPA CHUPS Кондит изд фрукт+кола 12г(Ван Мелле):100/1200,9605,9282,169,4,150
1000000000000001857,8000051717,LAF Резинка для волос Цветок СЛ в ассортименте (СИ):6/120,9292,464,8823,4,1
1000000000000008227,4000034766,LAF Точилка косметич д/каранд артPSP-003 в ассорт(СИ):3/360,9137,689,8424,0,24
1000000000000003735,4000094112,LAF Пилка маникюрная наждачная 180/220(СИ):6/288,8928,188,8740,0,0
1000000000000010781,8000015688,LAF Набор разноцв пилок для ногтей 200/240 5 шт (СИ):4/240,8640,2946,5681,40,-27
1000000000000005200,8000002452,LAF Beige Кисть для тональной основы и консилера (СИ):3/72,8569,388,8179,4,-2
1000000000000001789,1000580169,САМЫЙ СОК Гель для душа Витаминный коктейль Черника 200мл УЗ,8556,252,8300,0,4
1000000000000013768,8000002443,LAF Colour Кисть кабуки для пудры (СИ):4/96,8510,84,8426,0,0
1000000000000017678,8000112807,SUNDAY Стиральный порошок Автомат Универс Цветоч аром 5кг УЗ,8287,4730,3588,30,-61
1000000000000025545,8000009804,LAF Набор мини крабы 2шт Мрамор (СИ):4/240,8283,1614,6673,0,-4
1000000000000017688,4000094142,LAF Резинки для волос женские Вельвет 3 шт (СИ):3/240,8277,866,7410,0,1
1000000000000026173,8000107227,LAF Набор резинок для волос №1 2шт в асс УЗ,8230,279,7949,0,2
1000000000000001640,8000002431,LAF Спонж для макияжа в футляре 6шт треугольники (СИ):3/240,8158,18,8140,0,0
1000000000000006392,8000107230,LAF Набор резинка и заколка для волос №2 в асс УЗ,8088,177,7879,0,32
1000000000000018425,8000001315,LAF Набор резинок пружинок базовых 6 шт ШБ (СИ):12/480,8078,419,7671,0,-12
1000000000000004357,8000010388,LAF Краб для волос черный матовый База (СИ):3/240,8074,858,7216,0,0
1000000000000018627,8000002444,LAF Beige Кисть для пудры (СИ):4/72,8038,799,7242,0,-3
1000000000000020378,4000073386,LAF Заколки для волос жемчуг 2шт в асс(СИ):3/36,8028,648,7380,0,0
1000000000000006178,8000010416,LAF Краб для волос черный матовый большой База(СИ):3/240,8023,1006,7023,0,-6
1000000000000009771,8000010596,LAF Набор детских браслетов с декором 3шт(СИ):6/240,7842,854,6751,0,237
1000000000000007731,8000000951,LAF Крабы жемчужные мини в ШБ (СИ):10/160,7811,138,7675,0,-2
1000000000000008683,4000094125,LAF Набор маникюрный пилки 2шт в ассорт(СИ):6/216,7774,85,7689,0,0
1000000000000016679,1000570752,BONAQUA Вода питьевая с минералами н/газ 0.5л УЗ,7656,7148,504,0,4
1000000000000009694,4000094122,LAF Набор маникюрный мини ножницы/пилка алмазная(СИ):4/144,7654,406,7104,0,144
1000000000000002277,4000104317,LAF Резинки д/волос 3шт Жемчуг пружинка в асс-те(СИ):6/480,7652,35,7617,0,0
1000000000000013484,4000094121,LAF Книпсер маникюрный с пилкой(СИ):4/144,7625,363,7254,0,8
1000000000000023381,8000026108,LAF Ободок корона ДС5 (СИ):6/480,7618,180,7438,0,0
1000000000000004011,8000057559,LAF Набор резинок д/волос СЛ в асс-те (СИ):6/600,7523,693,6829,10,-9
1000000000000021685,1000582859,PERSIL Капсула для стирки Universal 1шт УЗ,7500,5592,900,60,948
1000000000000002742,4000094128,LAF Пемза для ног овальная (СИ):4/240,7456,1922,5531,0,3
1000000000000015198,1000187049,LA FRESH Ватные палочки 200шт п/уп (шнурок)(Белла): 48,7348,1811,5539,22,-24
1000000000000016966,4000104294,LAF Набор аксессуаров для волос 4 шт (СИ):4/480,7323,836,6494,0,-7
1000000000000015072,1000441981,SUNLIGHT Влажные салфетки карм Woman 2021 15х144 УЗ,7309,6980,326,210,-207
1000000000000012660,1000529247,LOREAL Elseve Шампунь д/вол гиалуон Pure 400мл:6,7300,3171,3554,1061,-486
1000000000000025235,8000048695,LAF Ободок детский ушки жемчуг перл ДС6 в асс (СИ):5/480,7229,786,5710,0,733
1000000000000025928,1000484216,LA FRESH Прокладки ежедневные гигиенические жен 20шт(СИ):36,7224,1307,5813,161,-57
1000000000000015108,8000010352,LAF Резинки д/волос 20шт тонкие черные(СИ):6/480,7200,598,6596,0,6
1000000000000010190,8000024698,LAF Набор резинок д/волос 2шт Бантики ДС5(СИ):6/480,7198,388,6810,0,0"""

# ──────────────────────────────────────────────────────────────────────────
# СТИЛИ — яркий динамичный интерфейс с анимациями
# ВАЖНО: все строки HTML/CSS начинаются БЕЗ отступа (с левого края).
# Если строка внутри st.markdown() начинается с 4+ пробелов, Streamlit
# (markdown/CommonMark) воспринимает её как БЛОК КОДА и печатает как
# обычный текст вместо того, чтобы отрендерить как HTML — именно из-за
# этого на дашборде "вылезали" сырые теги вроде </div>.
# ──────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

.stApp {
background: radial-gradient(1200px 600px at 10% -10%, rgba(167,139,250,0.14), transparent 60%),
            radial-gradient(1000px 500px at 100% 0%, rgba(34,211,238,0.12), transparent 55%),
            linear-gradient(180deg, #FBFAFF 0%, #F5F3FF 45%, #F0FBFF 100%);
background-color: #FBFAFF;
}

/* Заголовок */
.hero {
display: flex;
justify-content: space-between;
align-items: center;
padding: 28px 34px;
border-radius: 18px;
background: linear-gradient(135deg, #7C3AED 0%, #A855F7 45%, #22D3EE 100%);
border: 1px solid rgba(124,58,237,0.20);
box-shadow: 0 10px 32px rgba(124,58,237,0.25);
margin-bottom: 22px;
animation: fadeIn 0.6s ease;
position: relative;
overflow: hidden;
}
.hero::before {
content: "";
position: absolute;
top: -60%; left: -20%;
width: 60%; height: 220%;
background: linear-gradient(120deg, transparent, rgba(255,255,255,0.35), transparent);
animation: sheen 5s ease-in-out infinite;
}
@keyframes sheen {
0% { transform: translateX(-120%) rotate(8deg); }
50% { transform: translateX(220%) rotate(8deg); }
100% { transform: translateX(220%) rotate(8deg); }
}
.hero h1 {
color: #FFFFFF;
font-weight: 900;
font-size: 29px;
margin: 0;
letter-spacing: -0.3px;
text-shadow: 0 2px 12px rgba(0,0,0,0.12);
}
.hero p {
color: #F1EBFF;
margin: 5px 0 0 0;
font-size: 14px;
}
.hero-accent {
background: linear-gradient(90deg, #FDE68A, #FFFFFF, #A7F3D0);
background-size: 200% auto;
-webkit-background-clip: text;
-webkit-text-fill-color: transparent;
animation: shine 4s linear infinite;
}
@keyframes shine {
to { background-position: 200% center; }
}

@keyframes fadeIn {
from { opacity: 0; transform: translateY(-10px); }
to   { opacity: 1; transform: translateY(0); }
}
@keyframes fadeInUp {
from { opacity: 0; transform: translateY(14px) scale(0.98); }
to   { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes pulseGlow {
0%, 100% { box-shadow: 0 0 0 rgba(124,58,237,0); }
50% { box-shadow: 0 0 22px rgba(124,58,237,0.35); }
}

/* KPI карточки */
.kpi-card {
border-radius: 16px;
padding: 18px 20px;
background: #FFFFFF;
border: 1px solid rgba(124,58,237,0.12);
box-shadow: 0 4px 18px rgba(124,58,237,0.08);
animation: fadeInUp 0.5s ease both;
transition: border-color 0.2s ease, transform 0.2s ease, box-shadow 0.2s ease;
position: relative;
}
.kpi-card:nth-child(1) { animation-delay: 0.02s; }
.kpi-card:nth-child(2) { animation-delay: 0.08s; }
.kpi-card:nth-child(3) { animation-delay: 0.14s; }
.kpi-card:nth-child(4) { animation-delay: 0.20s; }
.kpi-card:nth-child(5) { animation-delay: 0.26s; }
.kpi-card:hover {
border-color: rgba(124,58,237,0.45);
transform: translateY(-3px);
box-shadow: 0 12px 28px rgba(124,58,237,0.18);
}
.kpi-label {
color: #6B6690;
font-size: 12.5px;
font-weight: 700;
text-transform: uppercase;
letter-spacing: 0.6px;
margin-bottom: 6px;
}
.kpi-value {
background: linear-gradient(90deg, #7C3AED, #4C1D95);
-webkit-background-clip: text;
-webkit-text-fill-color: transparent;
font-size: 27px;
font-weight: 900;
line-height: 1.15;
}
.kpi-sub { margin-top: 6px; font-size: 12px; font-weight: 700; }
.kpi-sub.pos { color: #16A34A; }
.kpi-sub.neg { color: #DC2626; }
.kpi-sub.neutral { color: #0891B2; }
.kpi-qty { margin-top: 3px; font-size: 11.5px; font-weight: 600; color: #8B87AE; }

/* Прогресс-полоски */
.prog-wrap {
background: rgba(124,58,237,0.10);
border-radius: 999px;
height: 9px;
width: 100%;
overflow: hidden;
margin-top: 10px;
}
.prog-bar {
height: 100%;
border-radius: 999px;
background-size: 200% auto;
animation: growBar 1s cubic-bezier(.22,1,.36,1) both, shimmerBar 2.5s linear infinite 1s;
}
@keyframes growBar { from { width: 0%; } }
@keyframes shimmerBar { to { background-position: 200% center; } }

/* Кнопки фильтра */
div.stButton > button {
border-radius: 10px !important;
font-weight: 700 !important;
background: #FFFFFF !important;
color: #4C1D95 !important;
border: 1px solid rgba(124,58,237,0.25) !important;
transition: all 0.18s ease !important;
}
div.stButton > button:hover {
transform: translateY(-2px);
border-color: rgba(124,58,237,0.7) !important;
box-shadow: 0 6px 16px rgba(124,58,237,0.22);
}
div.stButton > button[kind="primary"] {
background: linear-gradient(90deg, #7C3AED, #22D3EE) !important;
color: #FFFFFF !important;
border: none !important;
animation: pulseGlow 2.4s ease-in-out infinite;
}
div.stDownloadButton > button {
border-radius: 10px !important;
font-weight: 700 !important;
background: linear-gradient(90deg, #7C3AED, #22D3EE) !important;
color: #FFFFFF !important;
border: none !important;
transition: all 0.18s ease !important;
}
div.stDownloadButton > button:hover {
transform: translateY(-2px);
box-shadow: 0 6px 18px rgba(124,58,237,0.3);
}

section[data-testid="stSidebar"] {
background: #FFFFFF;
border-right: 1px solid rgba(124,58,237,0.10);
}

.summary-strip {
display: flex;
gap: 22px;
flex-wrap: wrap;
padding: 14px 18px;
border-radius: 12px;
background: #FFFFFF;
border: 1px solid rgba(124,58,237,0.14);
box-shadow: 0 4px 14px rgba(124,58,237,0.07);
margin: 10px 0 16px 0;
font-size: 14px;
color: #443F6B;
animation: fadeInUp 0.4s ease both;
}
.summary-strip b { color: #1E1B33; }

h1, h2, h3, h4, h5, p, span, label { color: #1E1B33; }

footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────
# ЗАГРУЗКА / НОРМАЛИЗАЦИЯ / АГРЕГАЦИЯ
# ──────────────────────────────────────────────────────────────────────────
def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename_map, used = {}, set()
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
    for internal in INTERNAL_COLS:
        if internal not in df.columns:
            df[internal] = 0
    return df[INTERNAL_COLS]


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


def clean_id(series: pd.Series) -> pd.Series:
    """Приводит СКЮ/код Магнита к чистой текстовой строке без
    научной нотации и хвостового '.0', даже если данные пришли как float.
    Обычные "чистые" строки (например, при чтении с dtype=str) не трогает,
    чтобы не терять точность длинных чисел через промежуточный float."""
    def _fix(v):
        s = str(v).strip()
        if s in ("", "nan", "None", "NaT"):
            return "0"
        if s.lstrip("-").isdigit():
            # уже чистое целое число в виде строки — не трогаем (без потери точности)
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
    if x < 0:
        return "Излишки"
    elif x > 0:
        return "Недостачи"
    return "Без расхождений"


def finalize(raw: pd.DataFrame) -> pd.DataFrame:
    df = normalize_columns(raw)
    for col in NUMERIC_COLS:
        df[col] = clean_numeric(df[col])
    for col in ["sku", "magnit_code"]:
        df[col] = clean_id(df[col])
    df["description"] = df["description"].fillna("0").astype(str).str.strip()
    df.loc[df["description"].isin(["", "nan", "None"]), "description"] = "0"
    for col in NUMERIC_COLS:
        df[col] = df[col].round(0).astype("int64")

    # Группировка по СКЮ / Код Магнита / Описания —
    # суммируем Потеряно и Рассхождения (и остальные числовые поля),
    # чтобы дубли по одному СКЮ не искажали аналитику.
    df = df.groupby(GROUP_COLS, as_index=False)[NUMERIC_COLS].sum()

    df["category"] = df["discrepancy"].apply(categorize)
    return df.reset_index(drop=True)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def load_from_sheet() -> tuple[pd.DataFrame, bool, dict]:
    """Возвращает (df, is_live, debug). is_live=False, если пришлось использовать демо-данные."""
    debug = {"url": SHEET_URL}
    try:
        resp = requests.get(SHEET_URL, timeout=20)
        debug["status_code"] = resp.status_code
        resp.raise_for_status()
        text = resp.text
        debug["response_preview"] = text[:300]
        debug["response_length"] = len(text)
        if text.strip().lower().startswith("<!doctype") or "<html" in text[:200].lower():
            debug["error"] = "Ответ похож на HTML-страницу (логин/доступ), а не на CSV"
            raise ValueError("no access")
        # dtype=str — критично: не даём pandas превращать длинные числовые
        # СКЮ/коды в float (что приводит к "1.0000e+18" и "123.0" при экспорте)
        raw = pd.read_csv(io.StringIO(text), dtype=str)
        debug["raw_columns"] = list(raw.columns)
        debug["raw_row_count"] = len(raw)
        final = finalize(raw)
        debug["final_row_count"] = len(final)
        return final, True, debug
    except Exception as e:
        debug["exception"] = f"{type(e).__name__}: {e}"
        raw = pd.read_csv(io.StringIO(SAMPLE_DATA_CSV), dtype=str)
        return finalize(raw), False, debug


def to_excel_bytes(sheets: dict, drop_cols: dict | None = None) -> bytes:
    """drop_cols: {sheet_name: [список отображаемых названий колонок, которые НЕ выгружать]}"""
    drop_cols = drop_cols or {}
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        workbook = writer.book
        header_fmt = workbook.add_format(
            {"bold": True, "bg_color": "#20242f", "font_color": "white",
             "border": 1, "align": "center", "valign": "vcenter"}
        )
        pos_fmt = workbook.add_format({"font_color": "#B91C1C"})
        neg_fmt = workbook.add_format({"font_color": "#15803D"})
        text_fmt = workbook.add_format({"num_format": "@"})  # текстовый формат ячейки

        id_display_cols = {DISPLAY_NAMES["sku"], DISPLAY_NAMES["magnit_code"]}

        for sheet_name, data in sheets.items():
            # Не выгружаем строки без описания (значение "0" — значит нет данных)
            data = data[data["description"] != "0"]
            # Сортировка от большего к меньшему по модулю расхождения
            data = data.reindex(data["discrepancy"].abs().sort_values(ascending=False).index)
            display_df = data.rename(columns=DISPLAY_NAMES).drop(columns=["category"], errors="ignore")
            for extra_col in drop_cols.get(sheet_name, []):
                display_df = display_df.drop(columns=[extra_col], errors="ignore")
            safe_name = sheet_name[:31]
            display_df.to_excel(writer, sheet_name=safe_name, index=False)
            ws = writer.sheets[safe_name]
            if len(display_df) == 0:
                for i, col in enumerate(display_df.columns):
                    ws.write(0, i, col, header_fmt)
                continue
            for i, col in enumerate(display_df.columns):
                ws.write(0, i, col, header_fmt)
                width = max(14, min(46, int(display_df[col].astype(str).str.len().max() or 14) + 2))
                ws.set_column(i, i, width)
                if col in id_display_cols:
                    # Перезаписываем ячейки колонки явно как ТЕКСТ, чтобы Excel
                    # не превращал длинные СКЮ/коды в число / научную нотацию
                    for r, val in enumerate(display_df[col].astype(str), start=1):
                        ws.write_string(r, i, val, text_fmt)
            if "Рассхождения" in display_df.columns and len(display_df) > 0:
                col_idx = list(display_df.columns).index("Рассхождения")
                ws.conditional_format(1, col_idx, len(display_df), col_idx,
                                       {"type": "cell", "criteria": "<", "value": 0, "format": neg_fmt})
                ws.conditional_format(1, col_idx, len(display_df), col_idx,
                                       {"type": "cell", "criteria": ">", "value": 0, "format": pos_fmt})
    return output.getvalue()


# ──────────────────────────────────────────────────────────────────────────
# ЗАГРУЖАЕМ ДАННЫЕ
# ──────────────────────────────────────────────────────────────────────────
df, is_live, debug_info = load_from_sheet()

# ──────────────────────────────────────────────────────────────────────────
# SIDEBAR — ТОЛЬКО ПОИСК
# ──────────────────────────────────────────────────────────────────────────
with st.sidebar:
    with st.expander("🔧 Диагностика загрузки", expanded=not is_live):
        st.json(debug_info)
    st.markdown("### 🔍 Поиск")
    search = st.text_input(
        "Поиск",
        placeholder="СКЮ, код Магнита или название…",
        label_visibility="collapsed",
    )
    st.caption(f"Обновлено: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    if not is_live:
        st.caption("⚠️ Показаны демо-данные (таблица недоступна)")

# ──────────────────────────────────────────────────────────────────────────
# HERO + КНОПКА ОБНОВИТЬ
# ──────────────────────────────────────────────────────────────────────────
if "filter_mode" not in st.session_state:
    st.session_state.filter_mode = "all"

hero_col1, hero_col2 = st.columns([5, 1])
with hero_col1:
    st.markdown("""
<div class="hero">
<div>
<h1>📦 Аналитика <span class="hero-accent">расхождений</span> СКЮ</h1>
<p>Принято → Отгружено → Сток → Потери → Расхождения</p>
</div>
</div>
""", unsafe_allow_html=True)
with hero_col2:
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    if st.button("🔄 Обновить данные", width="stretch"):
        st.cache_data.clear()
        st.rerun()

# ──────────────────────────────────────────────────────────────────────────
# КНОПКИ-ФИЛЬТРЫ ПО ТИПУ РАСХОЖДЕНИЯ
# ──────────────────────────────────────────────────────────────────────────
btn_cols = st.columns(4)
labels = [
    ("all", "📊 Все позиции"),
    ("excess", "📈 Излишки (—)"),
    ("shortage", "📉 Недостачи (+)"),
    ("loss", "⚠️ С потерями"),
]
for i, (key, label) in enumerate(labels):
    btn_type = "primary" if st.session_state.filter_mode == key else "secondary"
    if btn_cols[i].button(label, width="stretch", type=btn_type, key=f"btn_{key}"):
        st.session_state.filter_mode = key

mode = st.session_state.filter_mode

# ──────────────────────────────────────────────────────────────────────────
# ПРИМЕНЕНИЕ ФИЛЬТРОВ + ПОИСКА
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
        | filtered["description"].str.lower().str.contains(s, na=False)
    )
    filtered = filtered[mask]

filtered = filtered.reindex(filtered["discrepancy"].abs().sort_values(ascending=False).index)

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

qty_excess = abs(int(df.loc[df["discrepancy"] < 0, "discrepancy"].sum()))
qty_shortage = int(df.loc[df["discrepancy"] > 0, "discrepancy"].sum())
qty_lost = int(df["lost"].sum())
qty_total = int(df["stock"].sum())
qty_zero = int(df.loc[df["category"] == "Без расхождений", "stock"].sum())


def fmt(n):
    return f"{n:,}".replace(",", " ")


st.markdown("### 📈 Ключевые показатели")
kpi_cols = st.columns(5)
# (label, значение в шт, доп.строка "% · N СКЮ", цвет категории)
kpi_data = [
    ("Всего СКЮ", fmt(qty_total), f"{fmt(total)} СКЮ", "#4F46E5"),
    ("Излишки", fmt(qty_excess), f"{pct_excess:.1f}% · {fmt(excess_n)} СКЮ", "#16A34A"),
    ("Недостачи", fmt(qty_shortage), f"{pct_shortage:.1f}% · {fmt(shortage_n)} СКЮ", "#DC2626"),
    ("Без расхождений", fmt(qty_zero), f"{pct_zero:.1f}% · {fmt(zero_n)} СКЮ", "#0891B2"),
    ("С потерями", fmt(qty_lost), f"{pct_loss:.1f}% · {fmt(loss_n)} СКЮ", "#D97706"),
]
for col, (label, value, sub, color) in zip(kpi_cols, kpi_data):
    col.markdown(f"""
<div class="kpi-card" style="border-top:4px solid {color};">
<div class="kpi-label">{label}</div>
<div class="kpi-value" style="background:linear-gradient(90deg, {color}, {color}CC); -webkit-background-clip:text; -webkit-text-fill-color:transparent;">{value} <span style="font-size:14px; font-weight:700;">шт</span></div>
<div class="kpi-sub" style="color:{color};">{sub}</div>
</div>
""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

prog_col1, prog_col2, prog_col3 = st.columns(3)
progress_data = [
    (prog_col1, "Излишки", pct_excess, "#16A34A, #22C55E"),
    (prog_col2, "Недостачи", pct_shortage, "#DC2626, #F87171"),
    (prog_col3, "Потери", pct_loss, "#D97706, #F59E0B"),
]
for col, label, pct, color in progress_data:
    col.markdown(f"""
<div class="kpi-card">
<div class="kpi-label">Доля: {label}</div>
<div class="kpi-value" style="font-size:22px;">{pct:.1f}%</div>
<div class="prog-wrap"><div class="prog-bar" style="width:{pct:.1f}%; background:linear-gradient(90deg, {color});"></div></div>
</div>
""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────────────────
# ГРАФИКИ
# ──────────────────────────────────────────────────────────────────────────
st.markdown("#### 🍩 Структура расхождений, шт")
donut_df = pd.DataFrame({
    "Категория": ["Излишки", "Недостачи", "Без расхождений"],
    "Шт": [qty_excess, qty_shortage, qty_zero],
})
fig_donut = px.pie(
    donut_df, names="Категория", values="Шт", hole=0.6, color="Категория",
    color_discrete_map={"Излишки": "#16A34A", "Недостачи": "#DC2626", "Без расхождений": "#0891B2"},
)
fig_donut.update_traces(textposition="outside", textinfo="percent+label",
                         marker=dict(line=dict(color="#FFFFFF", width=2)))
fig_donut.update_layout(showlegend=False, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                         font_color="#1E1B33", margin=dict(t=10, b=10, l=10, r=10), height=340,
                         transition_duration=400)
st.plotly_chart(fig_donut, width="stretch")

st.markdown("<br>", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────
# ТАБЛИЦА + ИТОГИ ПО ВЫБОРКЕ
# ──────────────────────────────────────────────────────────────────────────
mode_titles = {
    "all": "Все позиции",
    "excess": "Излишки (расхождение со знаком «−»)",
    "shortage": "Недостачи (расхождение положительное)",
    "loss": "Позиции с потерями",
}
st.markdown(f"### 📋 {mode_titles[mode]} · найдено {fmt(len(filtered))}")

sum_lost_filtered = int(filtered["lost"].sum())
sum_disc_filtered = int(filtered["discrepancy"].sum())
excess_qty_filtered = abs(int(filtered.loc[filtered["discrepancy"] < 0, "discrepancy"].sum()))
shortage_qty_filtered = int(filtered.loc[filtered["discrepancy"] > 0, "discrepancy"].sum())
total_ent_filtered = excess_qty_filtered + shortage_qty_filtered + sum_lost_filtered
st.markdown(f"""
<div class="summary-strip">
<div>Итого <b>Потеряно</b>: <b>{fmt(sum_lost_filtered)}</b> шт</div>
<div>Итого <b>Рассхождения</b> (сумма): <b>{fmt(sum_disc_filtered)}</b> шт</div>
<div>Излишки + Недостачи + Потери: <b>{fmt(total_ent_filtered)}</b> шт</div>
</div>
""", unsafe_allow_html=True)

display_df = filtered.rename(columns=DISPLAY_NAMES).drop(columns=["category"], errors="ignore")


def highlight_disc(val):
    if isinstance(val, (int, float)):
        if val < 0:
            return "color:#16A34A; font-weight:700;"
        elif val > 0:
            return "color:#DC2626; font-weight:700;"
    return ""


styler = display_df.style
try:
    styled = styler.map(highlight_disc, subset=["Рассхождения"])
except AttributeError:
    styled = styler.applymap(highlight_disc, subset=["Рассхождения"])

st.dataframe(styled, width="stretch", height=420, hide_index=True)

# ──────────────────────────────────────────────────────────────────────────
# ЭКСПОРТ В EXCEL — раздельно по типам + текущий поиск/фильтр
# ──────────────────────────────────────────────────────────────────────────
st.markdown("### 📤 Выгрузка в Excel")
exp_col1, exp_col2, exp_col3, exp_col4 = st.columns(4)

ts = datetime.now().strftime("%Y%m%d_%H%M")

with exp_col1:
    data = df[df["discrepancy"] < 0]
    st.download_button(
        f"⬇️ Излишки ({fmt(len(data))})",
        data=to_excel_bytes({"Излишки": data}),
        file_name=f"izlishki_{ts}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )

with exp_col2:
    data = df[df["discrepancy"] > 0]
    st.download_button(
        f"⬇️ Недостачи ({fmt(len(data))})",
        data=to_excel_bytes({"Недостачи": data}),
        file_name=f"nedostachi_{ts}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )

with exp_col3:
    data = df[df["lost"] > 0]
    st.download_button(
        f"⬇️ Потери ({fmt(len(data))})",
        data=to_excel_bytes({"Потери": data}, drop_cols={"Потери": [DISPLAY_NAMES["discrepancy"]]}),
        file_name=f"poteri_{ts}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )

with exp_col4:
    st.download_button(
        f"⬇️ Текущий поиск/фильтр ({fmt(len(filtered))})",
        data=to_excel_bytes({mode_titles[mode][:31]: filtered}),
        file_name=f"poisk_{mode}_{ts}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )

st.markdown("""
<div style="text-align:center; color:#7C7A9E; margin-top:30px; font-size:12px;">
Данные обновляются из Google Таблицы каждые 5 минут
</div>
""", unsafe_allow_html=True)
