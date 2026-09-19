import streamlit as st
import streamlit.components.v1 as components
from PIL import Image
import io
import html
import os
from PIL import ImageDraw, ImageFont
import datetime
import sqlite3

try:
    import psycopg2
    import psycopg2.pool
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

# ============================================================
# Page Configuration
# ============================================================
st.set_page_config(
    page_title="Mom's Daily Kitchen",
    page_icon="🍲",
    layout="wide",
    initial_sidebar_state="expanded"
)

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MEAL_TYPES = ["Breakfast", "Lunch", "Dinner"]

# ============================================================
# Database Layer
# Supports SQLite (default, works out of the box) OR Postgres
# (e.g. a free Supabase project) for TRUE persistence across
# app restarts/redeploys. See README_PERSISTENCE.md for setup.
#
# To switch to Postgres: add a [postgres] section to
# .streamlit/secrets.toml with host/port/dbname/user/password.
# ============================================================

def using_postgres():
    return HAS_PSYCOPG2 and "postgres" in st.secrets

def q(query):
    """Translate a '?'-style query into '%s'-style for Postgres."""
    return query.replace("?", "%s") if using_postgres() else query

@st.cache_resource
def get_pg_pool():
    """
    A pool of already-open Postgres connections, cached for the life of
    the app process. Without this, every single database call had to pay
    for a brand-new network handshake to Supabase (the main cause of the
    slowdown after switching off local SQLite).
    """
    creds = st.secrets["postgres"]
    return psycopg2.pool.SimpleConnectionPool(
        1, 5,
        host=creds["host"],
        port=creds.get("port", 5432),
        dbname=creds["dbname"],
        user=creds["user"],
        password=creds["password"],
        sslmode="require",
    )

def get_connection():
    if using_postgres():
        return get_pg_pool().getconn()
    return sqlite3.connect("kitchen.db", check_same_thread=False)

def release_connection(conn):
    """Use instead of conn.close() so pooled Postgres connections go back
    into the pool for reuse instead of being torn down and reopened."""
    if using_postgres():
        get_pg_pool().putconn(conn)
    else:
        conn.close()

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    if using_postgres():
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recipes (
                id SERIAL PRIMARY KEY,
                name TEXT,
                category TEXT,
                meat TEXT,
                difficulty TEXT,
                time TEXT,
                ingredients TEXT,
                image BYTEA
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS weekly_plan (
                day TEXT,
                meal_type TEXT,
                recipe_id INTEGER,
                PRIMARY KEY (day, meal_type)
            )
        """)
    else:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recipes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                category TEXT,
                meat TEXT,
                difficulty TEXT,
                time TEXT,
                ingredients TEXT,
                image BLOB
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS weekly_plan (
                day TEXT,
                meal_type TEXT,
                recipe_id INTEGER,
                PRIMARY KEY (day, meal_type)
            )
        """)
    conn.commit()
    release_connection(conn)

init_db()

# ---------------- Recipe helpers ----------------

@st.cache_data(ttl=120)
def get_recipes():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, category, meat, difficulty, time, ingredients, image FROM recipes")
    rows = cursor.fetchall()
    release_connection(conn)
    recipes = []
    for row in rows:
        image_bytes = bytes(row[7]) if row[7] is not None else None
        recipes.append({
            "id": row[0],
            "name": row[1],
            "category": row[2],
            "meat": row[3],
            "difficulty": row[4],
            "time": row[5],
            "ingredients": row[6],
            "image": image_bytes,
        })
    return recipes

def compress_image(uploaded_file, max_dim=900, quality=80):
    """
    Shrink and re-encode an uploaded photo before it's stored. Phone photos
    are often several MB each, and every one of those bytes has to travel
    over the network to/from Supabase on every load — this is usually the
    single biggest thing slowing the app down once you have several
    recipes with photos. Resizing to a sensible display size and
    re-encoding as JPEG typically cuts file size by 80-95%, with no
    visible quality loss at the sizes this app displays images at.
    """
    img = Image.open(uploaded_file)
    img = img.convert("RGB")  # drop alpha channel; JPEG doesn't support it anyway
    img.thumbnail((max_dim, max_dim), Image.LANCZOS)
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()

# ============================================================
# Shopping-list image export
#
# Renders the shopping list as a shareable PNG (for WhatsApp/Telegram/
# Messenger) that matches the app's own look. This needs a font file that
# actually supports Khmer script bundled with the app — the system fonts
# on Streamlit Cloud don't include Khmer, so without this the text would
# render as empty boxes. The font lives at assets/KantumruyPro-Variable.ttf
# alongside this file; make sure that file is committed to your repo too.
FONT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "NotoSansKhmer-Variable.ttf")

_IMG_INK = (43, 38, 34)
_IMG_PAPER = (245, 241, 228)
_IMG_CARD_BG = (255, 253, 248)
_IMG_ROW_ALT = (251, 247, 238)
_IMG_HEADER_BG = (237, 230, 211)
_IMG_GOLD = (198, 138, 61)
_IMG_BORDER = (218, 209, 189)
_IMG_NUM_COLOR = (74, 68, 60)

def _get_khmer_font(size, weight=400):
    font = ImageFont.truetype(FONT_PATH, size)
    try:
        # Noto Sans Khmer's variable axes are [Weight, Width] in that order;
        # 100 keeps the width at its normal (non-condensed) setting.
        font.set_variation_by_axes([weight, 100])
    except Exception:
        pass
    return font

def _wrap_text(draw, text, font, max_width):
    words = text.split(" ")
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines

def generate_shopping_list_image(title, tbl_no_label, tbl_ing_label, ingredients):
    width = 640
    margin = 36
    card_width = width - margin * 2
    num_col_width = 64
    text_left_pad = 16
    text_max_width = card_width - num_col_width - text_left_pad - 16

    title_font = _get_khmer_font(24, 700)
    header_font = _get_khmer_font(15, 700)
    row_font = _get_khmer_font(15, 400)
    num_font = _get_khmer_font(15, 600)

    line_height = 21
    row_v_pad = 10
    header_height = 44
    title_block_height = 66

    dummy_img = Image.new("RGB", (10, 10))
    dummy_draw = ImageDraw.Draw(dummy_img)

    wrapped_rows = [_wrap_text(dummy_draw, ing, row_font, text_max_width) for ing in ingredients]
    row_heights = [max(1, len(lines)) * line_height + row_v_pad * 2 for lines in wrapped_rows]
    card_height = header_height + sum(row_heights)
    total_height = margin + title_block_height + card_height + margin

    img = Image.new("RGB", (width, total_height), _IMG_PAPER)
    draw = ImageDraw.Draw(img)

    for x in range(0, width, 18):
        for y in range(0, total_height, 18):
            draw.ellipse([x, y, x + 1, y + 1], fill=(231, 225, 208))

    bbox = draw.textbbox((0, 0), title, font=title_font)
    tw = bbox[2] - bbox[0]
    draw.text(((width - tw) / 2, margin + 12), title, font=title_font, fill=_IMG_INK)

    card_top = margin + title_block_height
    card_left = margin

    draw.rounded_rectangle(
        [card_left, card_top, card_left + card_width, card_top + card_height],
        radius=14, fill=_IMG_CARD_BG, outline=_IMG_BORDER, width=1
    )
    draw.rounded_rectangle(
        [card_left, card_top, card_left + card_width, card_top + header_height],
        radius=14, fill=_IMG_HEADER_BG, corners=(True, True, False, False)
    )
    draw.rectangle(
        [card_left, card_top + header_height - 14, card_left + card_width, card_top + header_height],
        fill=_IMG_HEADER_BG
    )
    draw.rectangle(
        [card_left, card_top + header_height - 2, card_left + card_width, card_top + header_height],
        fill=_IMG_GOLD
    )
    draw.line(
        [card_left + num_col_width, card_top, card_left + num_col_width, card_top + header_height],
        fill=_IMG_BORDER, width=1
    )
    draw.text((card_left + num_col_width / 2 - 8, card_top + 13), tbl_no_label, font=header_font, fill=_IMG_INK)
    draw.text((card_left + num_col_width + text_left_pad, card_top + 13), tbl_ing_label, font=header_font, fill=_IMG_INK)

    y = card_top + header_height
    for idx, lines in enumerate(wrapped_rows, 1):
        rh = row_heights[idx - 1]
        row_bg = _IMG_CARD_BG if idx % 2 else _IMG_ROW_ALT
        draw.rectangle([card_left + 1, y, card_left + card_width - 1, y + rh], fill=row_bg)
        draw.line([card_left, y + rh, card_left + card_width, y + rh], fill=_IMG_BORDER, width=1)
        draw.line([card_left + num_col_width, y, card_left + num_col_width, y + rh], fill=(232, 226, 210), width=1)

        num_str = str(idx)
        nbbox = draw.textbbox((0, 0), num_str, font=num_font)
        nw = nbbox[2] - nbbox[0]
        draw.text(
            (card_left + num_col_width / 2 - nw / 2, y + rh / 2 - (len(lines) * line_height) / 2 + 2),
            num_str, font=num_font, fill=_IMG_NUM_COLOR
        )

        text_y = y + row_v_pad
        for line in lines:
            draw.text((card_left + num_col_width + text_left_pad, text_y), line, font=row_font, fill=_IMG_INK)
            text_y += line_height

        y += rh

    draw.rounded_rectangle(
        [card_left, card_top, card_left + card_width, card_top + card_height],
        radius=14, outline=_IMG_BORDER, width=1
    )

    return img

def add_recipe_db(name, category, meat, difficulty, time, ingredients, image):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(q("""
        INSERT INTO recipes (name, category, meat, difficulty, time, ingredients, image)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """), (name, category, meat, difficulty, time, ingredients, image))
    conn.commit()
    release_connection(conn)
    get_recipes.clear()

def update_recipe_db(recipe_id, name, category, meat, difficulty, time, ingredients, image):
    conn = get_connection()
    cursor = conn.cursor()
    if image:
        cursor.execute(q("""
            UPDATE recipes SET name=?, category=?, meat=?, difficulty=?, time=?, ingredients=?, image=?
            WHERE id=?
        """), (name, category, meat, difficulty, time, ingredients, image, recipe_id))
    else:
        cursor.execute(q("""
            UPDATE recipes SET name=?, category=?, meat=?, difficulty=?, time=?, ingredients=?
            WHERE id=?
        """), (name, category, meat, difficulty, time, ingredients, recipe_id))
    conn.commit()
    release_connection(conn)
    get_recipes.clear()

def delete_recipe_db(recipe_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(q("DELETE FROM recipes WHERE id=?"), (recipe_id,))
    # Also clear any weekly plan slots pointing to this recipe
    cursor.execute(q("DELETE FROM weekly_plan WHERE recipe_id=?"), (recipe_id,))
    conn.commit()
    release_connection(conn)
    get_recipes.clear()
    get_weekly_plan.clear()

# ---------------- Weekly plan helpers (now backed by the DB, not just session_state) ----------------

@st.cache_data(ttl=120)
def get_weekly_plan():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT day, meal_type, recipe_id FROM weekly_plan")
    rows = cursor.fetchall()
    release_connection(conn)
    plan = {day: {m: None for m in MEAL_TYPES} for day in DAYS}
    for day, meal_type, recipe_id in rows:
        if day in plan and meal_type in MEAL_TYPES:
            plan[day][meal_type] = recipe_id
    return plan

def set_weekly_meal(day, meal_type, recipe_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(q("DELETE FROM weekly_plan WHERE day=? AND meal_type=?"), (day, meal_type))
    if recipe_id is not None:
        cursor.execute(q("INSERT INTO weekly_plan (day, meal_type, recipe_id) VALUES (?, ?, ?)"),
                        (day, meal_type, recipe_id))
    conn.commit()
    release_connection(conn)
    get_weekly_plan.clear()

def clear_day_db(day):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(q("DELETE FROM weekly_plan WHERE day=?"), (day,))
    conn.commit()
    release_connection(conn)
    get_weekly_plan.clear()

# ============================================================
# Professional Custom CSS Styling
# ============================================================
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Kantumruy+Pro:ital,wght@0,300;0,400;0,500;0,600;0,700;1,400&display=swap');

    :root {
        --ink: #2B2622;
        --paper: #F5F1E4;
        --panel: #EDE6D3;
        --terracotta: #A6553C;
        --terracotta-dark: #7E3E2C;
        --leaf: #3F5D45;
        --gold: #C68A3D;
        --chili: #8C2F2F;
    }

    html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"],
    p, li, label, span, div, h1, h2, h3, h4, h5, h6,
    button, input, textarea, select,
    [data-testid="stMarkdownContainer"] {
        font-family: 'Kantumruy Pro', sans-serif;
    }

    /* Don't let the font override above break Streamlit's own icon glyphs
       (e.g. the sidebar collapse arrow), which rely on a ligature icon font. */
    [data-testid="stIconMaterial"],
    .material-symbols-rounded,
    .material-symbols-outlined,
    [class*="material-symbols"] {
        font-family: 'Material Symbols Rounded' !important;
    }

    .main, [data-testid="stAppViewContainer"] {
        background-color: var(--paper);
        background-image: radial-gradient(rgba(43, 38, 34, 0.045) 1px, transparent 1px);
        background-size: 18px 18px;
    }

    [data-testid="stSidebar"] {
        background-color: var(--panel);
        border-right: 1px solid rgba(43, 38, 34, 0.08);
    }

    h1, h2, h3, h4 {
        color: var(--ink);
        font-family: 'Kantumruy Pro', sans-serif;
        font-weight: 700;
        letter-spacing: 0;
    }

    /* ---------- Hero header ---------- */
    .kitchen-hero {
        background: var(--ink);
        color: var(--paper);
        border-radius: 14px;
        padding: 0 40px 30px 40px;
        margin-bottom: 28px;
        position: relative;
        overflow: hidden;
    }
    .kitchen-hero__weave {
        height: 10px;
        width: 100%;
        background-image: repeating-linear-gradient(
            135deg,
            var(--gold) 0px, var(--gold) 8px,
            transparent 8px, transparent 16px
        );
        opacity: 0.55;
        margin-bottom: 26px;
    }
    .kitchen-hero__body {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 24px;
    }
    .kitchen-hero__pot {
        flex-shrink: 0;
        opacity: 0.9;
    }
    .kitchen-hero__rule {
        border: none;
        border-top: 2px solid var(--gold);
        border-bottom: 1px solid rgba(198, 138, 61, 0.4);
        height: 3px;
        width: 64px;
        margin: 0 0 18px 0;
    }
    .kitchen-hero__title {
        font-size: 34px;
        font-weight: 700;
        margin: 0 0 10px 0;
        color: #FBF8F0;
    }
    .kitchen-hero__subtitle {
        font-size: 15.5px;
        line-height: 1.6;
        color: #D9D2C2;
        max-width: 640px;
        margin: 0;
    }

    /* ---------- Tabs (modern pill style) ---------- */
    [data-testid="stTabs"] [role="tablist"],
    [data-baseweb="tab-list"] {
        gap: 4px !important;
        background-color: var(--panel) !important;
        border-bottom: none !important;
        border-radius: 999px !important;
        padding: 5px !important;
        display: inline-flex !important;
    }
    [data-testid="stTabs"] [role="tab"],
    [data-testid="stTabs"] button[data-baseweb="tab"],
    [data-baseweb="tab"] {
        font-weight: 600 !important;
        color: #6B6355 !important;
        background-color: transparent !important;
        border-radius: 999px !important;
        padding: 8px 18px !important;
        margin: 0 !important;
        transition: background-color 0.18s ease, color 0.18s ease !important;
    }
    [data-testid="stTabs"] [role="tab"]:hover,
    [data-testid="stTabs"] button[data-baseweb="tab"]:hover {
        color: var(--terracotta-dark) !important;
    }
    [data-testid="stTabs"] [role="tab"][aria-selected="true"],
    [data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] {
        color: #FBF8F0 !important;
        background-color: var(--terracotta) !important;
    }
    [data-testid="stTabs"] [role="tab"] p,
    [data-testid="stTabs"] button[data-baseweb="tab"] p {
        color: inherit !important;
    }
    [data-baseweb="tab-highlight"] {
        background-color: transparent !important;
        display: none !important;
    }
    [data-baseweb="tab-border"] {
        background-color: transparent !important;
        display: none !important;
    }
    [data-testid="stTabs"] {
        border-bottom: none !important;
    }
    [data-testid="stTabs"] > div {
        border-bottom: none !important;
        box-shadow: none !important;
    }

    /* ---------- Buttons ---------- */
    div.stButton > button, div[data-testid="stFormSubmitButton"] > button {
        background-color: var(--terracotta);
        color: #FBF8F0;
        border: none;
        border-radius: 10px;
        font-weight: 600;
        padding: 0.5rem 1.1rem;
        box-shadow: 0 2px 8px rgba(166, 85, 60, 0.25);
        transition: background-color 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease;
    }
    div.stButton > button:hover, div[data-testid="stFormSubmitButton"] > button:hover {
        background-color: var(--terracotta-dark);
        color: #FBF8F0;
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(166, 85, 60, 0.32);
    }
    div.stButton > button:active, div[data-testid="stFormSubmitButton"] > button:active {
        transform: translateY(0);
    }

    /* ---------- Recipe cards ---------- */
    .recipe-card {
        background-color: #FFFDF8;
        padding: 24px 26px;
        border-radius: 16px;
        border: 1px solid rgba(43, 38, 34, 0.08);
        border-left: 4px solid var(--terracotta);
        box-shadow: 0 2px 12px rgba(43, 38, 34, 0.06);
        margin-bottom: 20px;
        transition: transform 0.18s ease, box-shadow 0.18s ease;
    }
    .recipe-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 24px rgba(43, 38, 34, 0.1);
    }
    .recipe-card h3 {
        margin-top: 0;
    }
    .recipe-divider {
        border: none;
        border-top: 1px solid rgba(43, 38, 34, 0.1);
        margin: 14px 0;
    }

    /* ---------- Gallery cards (Recipe Library grid) ---------- */
    .gallery-card {
        background-color: #FFFDF8;
        border-radius: 16px;
        border: 1px solid rgba(43, 38, 34, 0.08);
        box-shadow: 0 2px 12px rgba(43, 38, 34, 0.06);
        overflow: hidden;
        margin-bottom: 22px;
        transition: transform 0.18s ease, box-shadow 0.18s ease;
    }
    .gallery-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 12px 26px rgba(43, 38, 34, 0.12);
    }
    .gallery-card__body {
        padding: 16px 18px 18px 18px;
    }
    .gallery-card__title {
        font-size: 17px;
        font-weight: 700;
        color: var(--ink);
        margin: 0 0 8px 0;
    }

    /* ---------- Shopping list table (screen size, big/full-width) ---------- */
    .shopping-table {
        width: 100%;
        border-collapse: collapse;
        background-color: #FFFDF8;
        border: 1px solid rgba(43, 38, 34, 0.1);
        border-radius: 10px;
        overflow: hidden;
    }
    .shopping-table thead tr {
        background-color: #EDE6D3;
        border-bottom: 2px solid #C68A3D;
    }
    .shopping-table th {
        padding: 14px;
        text-align: left;
        color: #2B2622;
        font-weight: 700;
    }
    .shopping-table th:first-child {
        text-align: center;
        width: 10%;
        border-right: 1px solid rgba(43, 38, 34, 0.1);
    }
    .shopping-table th:last-child {
        padding-left: 20px;
    }
    .shopping-table td {
        padding: 12px;
        color: #2B2622;
        border-bottom: 1px solid rgba(43, 38, 34, 0.08);
    }
    .shopping-table td:first-child {
        text-align: center;
        font-weight: 600;
        color: #4A443C;
        border-right: 1px solid rgba(43, 38, 34, 0.08);
    }
    .shopping-table td:last-child {
        padding-left: 20px;
    }
    .shopping-table tbody tr:nth-child(even) {
        background-color: #FBF7EE;
    }
    .shopping-table tbody tr:nth-child(odd) {
        background-color: #FFFDF8;
    }

    /* Title shown only inside the printed shopping list, not on screen
       (the on-screen page already has its own heading above the table). */
    .print-only-title {
        display: none;
    }
    .shopping-table-wrap {
        width: 100%;
    }

    /* ---------- Badges ---------- */
    .badge-category {
        background-color: rgba(63, 93, 69, 0.12);
        color: var(--leaf);
        padding: 6px 12px;
        border-radius: 8px;
        font-size: 12px;
        font-weight: 600;
        display: inline-block;
        margin-right: 6px;
        margin-bottom: 4px;
    }
    .badge-meat {
        background-color: rgba(166, 85, 60, 0.12);
        color: var(--terracotta-dark);
        padding: 6px 12px;
        border-radius: 8px;
        font-size: 12px;
        font-weight: 600;
        display: inline-block;
        margin-right: 6px;
        margin-bottom: 4px;
    }
    .badge-diff-Easy {
        background-color: rgba(63, 93, 69, 0.14);
        color: var(--leaf);
        padding: 6px 12px;
        border-radius: 8px;
        font-size: 12px;
        font-weight: 600;
        display: inline-block;
        margin-right: 6px;
        margin-bottom: 4px;
    }
    .badge-diff-Medium {
        background-color: rgba(198, 138, 61, 0.18);
        color: #8A5D22;
        padding: 6px 12px;
        border-radius: 8px;
        font-size: 12px;
        font-weight: 600;
        display: inline-block;
        margin-right: 6px;
        margin-bottom: 4px;
    }
    .badge-diff-Hard {
        background-color: rgba(140, 47, 47, 0.12);
        color: var(--chili);
        padding: 6px 12px;
        border-radius: 8px;
        font-size: 12px;
        font-weight: 600;
        display: inline-block;
        margin-right: 6px;
        margin-bottom: 4px;
    }
    .badge-time {
        background-color: rgba(43, 38, 34, 0.07);
        color: #4A443C;
        padding: 6px 12px;
        border-radius: 8px;
        font-size: 12px;
        font-weight: 600;
        display: inline-block;
        margin-bottom: 4px;
    }

    /* ---------- Alerts ---------- */
    [data-testid="stAlert"] {
        border-radius: 8px;
    }

    /* ---------- No-image placeholder ---------- */
    .no-image-box {
        background-color: rgba(43, 38, 34, 0.04);
        border: 1px dashed rgba(43, 38, 34, 0.2);
        border-radius: 10px;
        padding: 28px 10px;
        text-align: center;
        font-size: 26px;
        color: #A69D8B;
    }
    .no-image-box span {
        display: block;
        font-size: 12px;
        margin-top: 6px;
        color: #8A8172;
    }

    /* ---------- Forms as quiet cards ---------- */
    [data-testid="stForm"] {
        background-color: #FFFDF8;
        border: 1px solid rgba(43, 38, 34, 0.1);
        border-radius: 14px;
        padding: 22px 24px 8px 24px;
    }

    /* ---------- Bordered containers (weekly planner day cards) ---------- */
    [data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 14px !important;
        border-color: rgba(43, 38, 34, 0.12) !important;
        background-color: #FFFDF8;
        transition: box-shadow 0.18s ease;
    }
    [data-testid="stVerticalBlockBorderWrapper"]:hover {
        box-shadow: 0 6px 18px rgba(43, 38, 34, 0.08);
    }

    /* ---------- Inputs ---------- */
    div[data-baseweb="select"] > div,
    div[data-baseweb="input"] > div,
    textarea {
        border-radius: 8px !important;
    }
    div[data-baseweb="select"]:focus-within > div,
    div[data-baseweb="input"]:focus-within > div,
    textarea:focus {
        border-color: var(--terracotta) !important;
        box-shadow: 0 0 0 1px var(--terracotta) !important;
    }

    /* ---------- Print: only the shopping list, nothing else ---------- */
    @media print {
        body * {
            visibility: hidden;
        }
        #printable-shopping-list, #printable-shopping-list * {
            visibility: visible;
        }
        #printable-shopping-list {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
        }
        .shopping-table-wrap {
            max-width: 640px !important;
            margin: 0 auto !important;
        }
        .shopping-table {
            font-size: 14.5px !important;
            border-color: rgba(43, 38, 34, 0.18) !important;
        }
        .shopping-table th, .shopping-table td {
            padding: 8px 12px !important;
        }
        .print-only-title {
            display: block !important;
            font-size: 20px;
            font-weight: 700;
            color: #2B2622;
            text-align: center;
            margin-bottom: 16px;
            font-family: 'Kantumruy Pro', sans-serif;
        }
        /* These sit above/beside the printable content and reserve blank
           space even while hidden via visibility, so remove them from the
           layout entirely instead. */
        .kitchen-hero,
        [data-testid="stSidebar"],
        [data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-baseweb="tab-list"] {
            display: none !important;
        }
        /* Streamlit reserves top padding on its main container regardless
           of the toolbar's own visibility — zero it out for print. */
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        .main .block-container,
        [data-testid="block-container"] {
            padding-top: 0 !important;
            margin-top: 0 !important;
        }
    }
    </style>
""", unsafe_allow_html=True)

# ============================================================
# Translation Dictionaries
# ============================================================
LANG = {
    "English": {
        "title": "🍲 Mom's Daily Kitchen",
        "subtitle": "Organize family recipes, view today's meals instantly, and keep everyday cooking effortless.",
        "tab1": "🏠 Today's Menu",
        "tab2": "📅 Weekly Planner",
        "tab3": "📖 Recipe Library",
        "tab4": "➕ Add New Dish",
        "tab5": "🛒 Shopping List",
        "view_for": "Viewing Meals For:",
        "breakfast": "Breakfast",
        "lunch": "Lunch",
        "dinner": "Dinner",
        "no_recipe": "No recipe assigned for",
        "visit_planner": "Visit the Weekly Planner tab to set one!",
        "filter_cat": "Filter by Cooking Type",
        "filter_meat": "Filter by Meat Type",
        "filter_diff": "Filter by Difficulty",
        "ingredients": "Ingredients",
        "time": "Time Needed",
        "difficulty": "Difficulty",
        "meat": "Meat/Protein",
        "category": "Cooking Type",
        "add_header": "Add a New Family Recipe",
        "add_sub": "Fill out the details below to add a new dish to the digital library.",
        "dish_name": "Dish Name *",
        "meat_type": "Main Meat / Protein (Choose one or more)",
        "cat_type": "Cooking Type Category",
        "diff_level": "Difficulty Level",
        "photo": "Upload Dish Photo",
        "ingredients_list": "Ingredients List",
        "save_btn": "Save Recipe to Library",
        "success_add": "Successfully added",
        "error_name": "Please provide at least a dish name.",
        "all": "All",
        "easy": "Easy",
        "medium": "Medium",
        "hard": "Hard",
        "no_image": "No Image",
        "weekly_header": "Weekly Schedule",
        "weekly_sub": "Assign saved recipes to breakfast, lunch, and dinner for every day of the week. Changes save automatically.",
        "no_food_msg": "There's no food for that type of meat or cooking yet. Please go add some!",
        "shopping_header": "Weekly Grocery Shopping List",
        "shopping_sub": "Automatically compiled deduplicated ingredient list based on your scheduled weekly meal plan.",
        "no_shopping": "No meals scheduled in the weekly planner yet, so the shopping list is empty!",
        "clear_day": "Clear Day",
        "tbl_no": "No.",
        "tbl_ing": "Ingredient",
        "confirm_delete": "Are you sure you want to delete this recipe? This cannot be undone.",
        "yes_delete": "Yes, delete it",
        "cancel": "Cancel",
        "saved": "Saved",
    },
    "Khmer (ភាសាខ្មែរ)": {
        "title": "🍲 ផ្ទះបាយប្រចាំថ្ងៃរបស់ម៉ាក់",
        "subtitle": "រៀបចំរូបមន្តម្ហូបគ្រួសារ មើលមុខម្ហូបថ្ងៃនេះភ្លាមៗ និងធ្វើឱ្យការធ្វើម្ហូបប្រចាំថ្ងៃកាន់តែងាយស្រួល។",
        "tab1": "🏠 មុខម្ហូបថ្ងៃនេះ",
        "tab2": "📅 ផែនការប្រចាំសប្តាហ៍",
        "tab3": "📖 បញ្ជីមុខម្ហូប",
        "tab4": "➕ បន្ថែមមុខម្ហូបថ្មី",
        "tab5": "🛒 បញ្ជីទិញទំនិញ",
        "view_for": "កំពុងមើលមុខម្ហូបសម្រាប់ថ្ងៃ៖",
        "breakfast": "អាហារពេលព្រឹក",
        "lunch": "អាហារថ្ងៃត្រង់",
        "dinner": "អាហារពេលល្ងាច",
        "no_recipe": "មិនទាន់មានមុខម្ហូបសម្រាប់",
        "visit_planner": "សូមចូលទៅកាន់ផ្ទាំងផែនការប្រចាំសប្តាហ៍ដើម្បីកំណត់!",
        "filter_cat": "ត្រងតាមប្រភេទម្ហូប",
        "filter_meat": "ត្រងតាមប្រភេទសាច់",
        "filter_diff": "ត្រងតាមកម្រិតពិបាក",
        "ingredients": "គ្រឿងផ្សំ",
        "time": "រយៈពេល",
        "difficulty": "កម្រិតពិបាក",
        "meat": "សាច់/ប្រូតេអ៊ីន",
        "category": "ប្រភេទម្ហូប",
        "add_header": "បន្ថែមមុខម្ហូបគ្រួសារថ្មី",
        "add_sub": "បំពេញព័ត៌មានលម្អិតខាងក្រោមដើម្បីបន្ថែមមុខម្ហូបថ្មីទៅក្នុងបណ្ណាល័យ។",
        "dish_name": "ឈ្មោះមុខម្ហូប *",
        "meat_type": "ប្រភេទសាច់ / ប្រូតេអ៊ីន (អាចជ្រើសរើសច្រើន)",
        "cat_type": "ប្រភេទចម្អិន",
        "diff_level": "កម្រិតពិបាក",
        "photo": "បញ្ចូលរូបភាពមុខម្ហូប",
        "ingredients_list": "បញ្ជីគ្រឿងផ្សំ",
        "save_btn": "រក្សាទុកមុខម្ហូប",
        "success_add": "បានបន្ថែមដោយជោគជ័យ៖",
        "error_name": "សូមបញ្ចូលឈ្មោះមុខម្ហូបយ៉ាងហោចណាស់មួយ។",
        "all": "ទាំងអស់",
        "easy": "ងាយស្រួល",
        "medium": "មធ្យម",
        "hard": "ពិបាក",
        "no_image": "គ្មានរូបភាព",
        "weekly_header": "កាលវិភាគប្រចាំសប្តាហ៍",
        "weekly_sub": "កំណត់មុខម្ហូបសម្រាប់ពេលព្រឹក ថ្ងៃត្រង់ និងល្ងាចសម្រាប់ថ្ងៃនីមួយៗក្នុងសប្តាហ៍។ ការផ្លាស់ប្តូររក្សាទុកដោយស្វ័យប្រវត្តិ។",
        "no_food_msg": "មិនទាន់មានម្ហូបសម្រាប់ប្រភេទសាច់ ឬប្រភេទចម្អិននេះនៅឡើយទេ សូមអញ្ជើញទៅបន្ថែម!",
        "shopping_header": "បញ្ជីទិញទំនិញផ្សារប្រចាំសប្តាហ៍",
        "shopping_sub": "បញ្ជីគ្រឿងផ្សំសរុបដែលបានចម្រាញ់រួចត្រូវបានចងក្រងដោយស្វ័យប្រវត្តិយោងតាមកាលវិភាគរបស់អ្នក។",
        "no_shopping": "មិនទាន់មានមុខម្ហូបកំណត់ក្នុងកាលវិភាគប្រចាំសប្តាហ៍នៅឡើយទេ!",
        "clear_day": "សម្អាតថ្ងៃនេះ",
        "tbl_no": "ល.រ",
        "tbl_ing": "គ្រឿងផ្សំ",
        "confirm_delete": "តើអ្នកប្រាកដថាចង់លុបមុខម្ហូបនេះមែនទេ? សកម្មភាពនេះមិនអាចត្រឡប់វិញបានទេ។",
        "yes_delete": "បាទ/ចាស លុបវា",
        "cancel": "បោះបង់",
        "saved": "បានរក្សាទុក",
    }
}

# ============================================================
# Sidebar: Live Clock & Language Selection
# ============================================================
with st.sidebar:
    components.html("""
        <div style="background: #FFFDF8; padding: 14px; border-radius: 10px; text-align: center; border: 1px solid rgba(43,38,34,0.1); border-top: 2px solid #C68A3D;">
            <p style="margin: 0; font-size: 12px; color: #6B6355; font-family: 'Kantumruy Pro', sans-serif;">Time now / ម៉ោងឥឡូវនេះ</p>
            <div id="live-clock" style="font-size: 17px; font-weight: 700; color: #2B2622; font-family: 'Kantumruy Pro', sans-serif; margin-top: 4px;"></div>
        </div>
        <script>
        function updateClock() {
            const now = new Date();
            document.getElementById('live-clock').innerHTML = now.toLocaleTimeString();
        }
        setInterval(updateClock, 1000);
        updateClock();
        </script>
    """, height=75)

    st.title("🌐 Language / ភាសា")
    selected_lang = st.selectbox("Choose Language", ["Khmer (ភាសាខ្មែរ)", "English"])

    if not using_postgres():
        st.warning(
            "⚠️ Running on local storage. Recipes may be lost if the app "
            "restarts. See README_PERSISTENCE.md to enable permanent cloud storage.",
            icon="⚠️",
        )

t = LANG[selected_lang]

day_display_map = {
    "Monday": "ថ្ងៃច័ន្ទ (Monday)",
    "Tuesday": "ថ្ងៃអង្គារ (Tuesday)",
    "Wednesday": "ថ្ងៃពុធ (Wednesday)",
    "Thursday": "ថ្ងៃព្រហស្បតិ៍ (Thursday)",
    "Friday": "ថ្ងៃសុក្រ (Friday)",
    "Saturday": "ថ្ងៃសៅរ៍ (Saturday)",
    "Sunday": "ថ្ងៃអាទិត្យ (Sunday)"
} if "Khmer" in selected_lang else {d: d for d in DAYS}

# Predefined Complete Option Lists for Categories and Meats
CATEGORY_OPTIONS = ["ប្រភេទ ឆា (Stir-Fried)", "ប្រភេទ អាំង (Grilled)", "ប្រភេទ ចៀន (Deep-Fried)", "ប្រភេទ សម្ល (Soup)", "ប្រភេទ ខ (Stew)", "ប្រភេទ ភ្លា (Salad)", "ប្រភេទ គ្រឿងសមុទ្រ (Seafood)", "ម្ហូបខ្មែរ (Khmer)", "ហូប បន្ថែម (Other)"]
MEAT_OPTIONS = ["សាច់ជ្រូក (Pork)", "សាច់មាន់ (Chicken)", "សាច់គោ (Beef)", "ត្រី / គ្រឿងសមុទ្រ (Fish / Seafood)", "បន្លែ / គ្មានសាច់ (Vegetarian / Other)"]

# App Header / Hero Section
st.markdown(f"""
    <div class="kitchen-hero">
        <div class="kitchen-hero__weave"></div>
        <div class="kitchen-hero__body">
            <div>
                <hr class="kitchen-hero__rule" />
                <p class="kitchen-hero__title">{html.escape(t["title"])}</p>
                <p class="kitchen-hero__subtitle">{html.escape(t["subtitle"])}</p>
            </div>
            <svg class="kitchen-hero__pot" width="72" height="72" viewBox="0 0 72 72" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M14 30 Q10 52 24 58 Q36 62 48 58 Q62 52 58 30" stroke="#C68A3D" stroke-width="2.2" stroke-linecap="round"/>
                <ellipse cx="36" cy="30" rx="24" ry="5" stroke="#C68A3D" stroke-width="2.2"/>
                <path d="M12 27 Q8 27 8 22" stroke="#C68A3D" stroke-width="2.2" stroke-linecap="round"/>
                <path d="M60 27 Q64 27 64 22" stroke="#C68A3D" stroke-width="2.2" stroke-linecap="round"/>
                <path d="M28 16 Q25 10 29 5" stroke="#D9D2C2" stroke-width="2" stroke-linecap="round" opacity="0.7"/>
                <path d="M38 16 Q35 9 39 3" stroke="#D9D2C2" stroke-width="2" stroke-linecap="round" opacity="0.5"/>
                <path d="M47 16 Q44 10 48 5" stroke="#D9D2C2" stroke-width="2" stroke-linecap="round" opacity="0.6"/>
            </svg>
        </div>
    </div>
""", unsafe_allow_html=True)

# Navigation Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([t["tab1"], t["tab2"], t["tab3"], t["tab4"], t["tab5"]])

# --- TAB 1: TODAY'S MENU (MAIN HOME TAB) ---
with tab1:
    st.subheader(t["tab1"])

    today_name = datetime.date.today().strftime("%A")
    default_index = DAYS.index(today_name) if today_name in DAYS else 0

    selected_view_day = st.selectbox(
        t["view_for"],
        DAYS,
        index=default_index,
        format_func=lambda x: day_display_map[x]
    )

    st.markdown(f"### 🍽️ {day_display_map[selected_view_day]}")
    st.write("")

    weekly_plan = get_weekly_plan()
    day_meals = weekly_plan.get(selected_view_day, {})
    recipes_list = get_recipes()
    recipes_by_id = {r["id"]: r for r in recipes_list}

    def render_today_meal(meal_type_label, meal_key):
        recipe_id = day_meals.get(meal_key)
        st.markdown(f"#### ⏰ {meal_type_label}")
        if recipe_id is not None:
            recipe = recipes_by_id.get(recipe_id)
            if recipe:
                st.markdown('<div class="recipe-card">', unsafe_allow_html=True)
                rc_col1, rc_col2 = st.columns([1, 3])

                with rc_col1:
                    if recipe["image"]:
                        img = Image.open(io.BytesIO(recipe["image"]))
                        st.image(img, use_container_width=True)
                    else:
                        st.markdown(
                            f'<div class="no-image-box">🍽️<br><span>{html.escape(t["no_image"])}</span></div>',
                            unsafe_allow_html=True,
                        )

                with rc_col2:
                    st.markdown(f"### {html.escape(recipe['name'])}")
                    cat_badge = f'<span class="badge-category">🍳 {html.escape(recipe.get("category", "General"))}</span>'

                    meat_vals = [m.strip() for m in recipe["meat"].split(",") if m.strip()]
                    meat_badges = "".join([f'<span class="badge-meat">🥩 {html.escape(m)}</span>' for m in meat_vals])

                    diff_badge = f'<span class="badge-diff-{recipe["difficulty"]}">⚡ {html.escape(recipe["difficulty"])}</span>'
                    time_badge = f'<span class="badge-time">⏱️ {html.escape(recipe["time"])}</span>'
                    st.markdown(f"{cat_badge} {meat_badges} {diff_badge} {time_badge}", unsafe_allow_html=True)
                    st.markdown("<hr class='recipe-divider' />", unsafe_allow_html=True)
                    st.markdown(f"**{t['ingredients']}:**\n{recipe['ingredients']}")

                st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.info("The recipe assigned here was removed.")
        else:
            st.info(f"{t['no_recipe']} {meal_type_label}. {t['visit_planner']}")
        st.divider()

    render_today_meal(t["breakfast"], "Breakfast")
    render_today_meal(t["lunch"], "Lunch")
    render_today_meal(t["dinner"], "Dinner")

# --- TAB 2: WEEKLY MEAL PLANNER ---
with tab2:
    st.subheader(t["weekly_header"])
    st.markdown(t["weekly_sub"])

    recipes_list = get_recipes()
    # Options are recipe IDs (None = empty). Names are only used for display.
    recipe_options = [None] + [r["id"] for r in recipes_list]
    recipe_name_by_id = {r["id"]: r["name"] for r in recipes_list}

    def format_recipe_option(rid):
        if rid is None:
            return "—"
        return recipe_name_by_id.get(rid, "(deleted recipe)")

    weekly_plan = get_weekly_plan()
    col_days = st.columns(2)

    for idx, day in enumerate(DAYS):
        # A per-day "generation" counter. Bumping this changes the selectbox
        # keys below, which forces Streamlit to treat them as brand-new
        # widgets with no memory of the previous pick — the reliable way to
        # force a dropdown back to blank, since just clearing session_state
        # for the old key isn't always enough on its own.
        reset_key = f"planner_gen_{day}"
        if reset_key not in st.session_state:
            st.session_state[reset_key] = 0

        with col_days[idx % 2]:
            with st.container(border=True):
                st.markdown(f"### 🗓️ {day_display_map[day]}")

                if st.button(f"🧹 {t['clear_day']}", key=f"clear_btn_{day}"):
                    clear_day_db(day)
                    st.session_state[reset_key] += 1
                    st.success(f"Cleared {day_display_map[day]}!")
                    st.rerun()

                for meal_type, label_key in zip(MEAL_TYPES, ["breakfast", "lunch", "dinner"]):
                    current_value = weekly_plan[day][meal_type]
                    # Guard against a stale id that no longer exists (e.g. recipe deleted)
                    if current_value not in recipe_options:
                        current_value = None
                    current_index = recipe_options.index(current_value)

                    new_value = st.selectbox(
                        f"{t[label_key]} ({day_display_map[day]})",
                        recipe_options,
                        index=current_index,
                        format_func=format_recipe_option,
                        key=f"{label_key}_{day}_{st.session_state[reset_key]}",
                    )

                    if new_value != current_value:
                        set_weekly_meal(day, meal_type, new_value)
                        st.toast(f"✅ {t['saved']}", icon="✅")
                        st.rerun()

                st.divider()

# --- TAB 3: RECIPE LIBRARY WITH EDITING ---
with tab3:
    st.subheader(t["tab3"])

    recipes_list = get_recipes()
    if not recipes_list:
        st.info("No recipes available yet. Go to 'Add New Dish' to start typing your own recipes!")
    else:
        f_col1, f_col2, f_col3 = st.columns(3)

        with f_col1:
            selected_cat = st.selectbox(t["filter_cat"], [t["all"]] + CATEGORY_OPTIONS)
        with f_col2:
            selected_meat = st.selectbox(t["filter_meat"], [t["all"]] + MEAT_OPTIONS)
        with f_col3:
            selected_diff = st.selectbox(t["filter_diff"], [t["all"], t["easy"], t["medium"], t["hard"]])

        filtered = recipes_list
        if selected_cat != t["all"]:
            filtered = [r for r in filtered if r.get("category", "") == selected_cat]
        if selected_meat != t["all"]:
            filtered = [r for r in filtered if selected_meat in r.get("meat", "")]
        if selected_diff != t["all"]:
            diff_map_reverse = {t["easy"]: "Easy", t["medium"]: "Medium", t["hard"]: "Hard"}
            eng_diff = diff_map_reverse.get(selected_diff, selected_diff)
            filtered = [r for r in filtered if r["difficulty"] == eng_diff]

        st.write("")

        if not filtered:
            st.warning(t["no_food_msg"])
        else:
            cols_per_row = 3
            recipe_rows = [filtered[i:i + cols_per_row] for i in range(0, len(filtered), cols_per_row)]

            for recipe_row in recipe_rows:
                cols = st.columns(cols_per_row)
                for col, recipe in zip(cols, recipe_row):
                    recipe_id = recipe["id"]
                    with col:
                        st.markdown('<div class="gallery-card">', unsafe_allow_html=True)

                        if recipe["image"]:
                            img = Image.open(io.BytesIO(recipe["image"]))
                            st.image(img, use_container_width=True)
                        else:
                            st.markdown(
                                f'<div class="no-image-box">🍽️<br><span>{html.escape(t["no_image"])}</span></div>',
                                unsafe_allow_html=True,
                            )

                        cat_badge = f'<span class="badge-category">🍳 {html.escape(recipe.get("category", "General"))}</span>'
                        meat_vals = [m.strip() for m in recipe["meat"].split(",") if m.strip()]
                        meat_badges = "".join([f'<span class="badge-meat">🥩 {html.escape(m)}</span>' for m in meat_vals])
                        diff_badge = f'<span class="badge-diff-{recipe["difficulty"]}">⚡ {html.escape(recipe["difficulty"])}</span>'
                        time_badge = f'<span class="badge-time">⏱️ {html.escape(recipe["time"])}</span>'

                        st.markdown(
                            f'<div class="gallery-card__body">'
                            f'<p class="gallery-card__title">{html.escape(recipe["name"])}</p>'
                            f'{cat_badge} {meat_badges} {diff_badge} {time_badge}'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                        with st.expander(f"🔍 {t['ingredients']} & edit"):
                            st.markdown(f"**{t['ingredients']}:**\n{recipe['ingredients']}")
                            st.markdown("<hr class='recipe-divider' />", unsafe_allow_html=True)

                            with st.form(f"edit_form_{recipe_id}"):
                                new_name = st.text_input("Dish Name", value=recipe["name"])

                                cat_idx = CATEGORY_OPTIONS.index(recipe["category"]) if recipe["category"] in CATEGORY_OPTIONS else 0
                                new_cat = st.selectbox("Category / Type", options=CATEGORY_OPTIONS, index=cat_idx, key=f"cat_{recipe_id}")

                                current_meats = [m.strip() for m in recipe["meat"].split(",") if m.strip() in MEAT_OPTIONS]
                                new_meats = st.multiselect("Meat / Protein", options=MEAT_OPTIONS, default=current_meats, key=f"meat_{recipe_id}")

                                diff_options = ["Easy", "Medium", "Hard"]
                                diff_idx = diff_options.index(recipe["difficulty"]) if recipe["difficulty"] in diff_options else 0
                                new_diff = st.selectbox("Difficulty", options=diff_options, index=diff_idx, key=f"diff_{recipe_id}")

                                new_time = st.text_input("Time Needed", value=recipe["time"], key=f"time_{recipe_id}")
                                new_ingredients = st.text_area("Ingredients", value=recipe["ingredients"], key=f"ing_{recipe_id}")
                                new_image = st.file_uploader("Update Photo (Optional)", type=["png", "jpg", "jpeg"], key=f"img_edit_{recipe_id}")

                                update_submitted = st.form_submit_button("Save Changes")
                                if update_submitted:
                                    if not new_name.strip():
                                        st.error(t["error_name"])
                                    else:
                                        img_bytes = compress_image(new_image) if new_image else None
                                        meat_str = ", ".join(new_meats) if new_meats else "None"
                                        update_recipe_db(recipe_id, new_name.strip(), new_cat, meat_str, new_diff, new_time, new_ingredients, img_bytes)
                                        st.success("Recipe updated successfully!")
                                        st.rerun()

                            # --- Delete with confirmation, so a stray tap can't wipe a recipe ---
                            confirm_key = f"confirm_del_{recipe_id}"
                            if st.session_state.get(confirm_key):
                                st.warning(t["confirm_delete"])
                                dcol1, dcol2 = st.columns(2)
                                with dcol1:
                                    if st.button(f"✅ {t['yes_delete']}", key=f"yes_del_{recipe_id}"):
                                        delete_recipe_db(recipe_id)
                                        st.session_state.pop(confirm_key, None)
                                        st.rerun()
                                with dcol2:
                                    if st.button(f"↩️ {t['cancel']}", key=f"cancel_del_{recipe_id}"):
                                        st.session_state.pop(confirm_key, None)
                                        st.rerun()
                            else:
                                if st.button("🗑️ Delete Recipe", key=f"del_{recipe_id}"):
                                    st.session_state[confirm_key] = True
                                    st.rerun()

                        st.markdown('</div>', unsafe_allow_html=True)

# --- TAB 4: ADD NEW DISH ---
with tab4:
    st.subheader(t["add_header"])
    st.markdown(t["add_sub"])

    with st.form("professional_recipe_form", clear_on_submit=True):
        form_col1, form_col2 = st.columns(2)

        with form_col1:
            dish_name = st.text_input(t["dish_name"], placeholder="e.g., ឆាត្រកួន")
            cat_type = st.selectbox(t["cat_type"], options=CATEGORY_OPTIONS)
            meat_types = st.multiselect(t["meat_type"], options=MEAT_OPTIONS, default=["សាច់ជ្រូក (Pork)"])

        with form_col2:
            difficulty = st.select_slider(t["diff_level"], options=["Easy", "Medium", "Hard"])
            prep_time = st.text_input(t["time"], placeholder="e.g., 20 mins")
            image_file = st.file_uploader(t["photo"], type=["png", "jpg", "jpeg"])

        ingredients = st.text_area(t["ingredients_list"], placeholder="Type ingredients separated by commas or new lines...")

        submitted = st.form_submit_button(t["save_btn"], use_container_width=True)

        if submitted:
            if dish_name.strip():
                img_bytes = compress_image(image_file) if image_file else None
                meat_str = ", ".join(meat_types) if meat_types else "None"
                add_recipe_db(dish_name.strip(), cat_type, meat_str, difficulty, prep_time if prep_time else "Quick", ingredients if ingredients else "Not specified", img_bytes)
                st.success(f"{t['success_add']} '{dish_name.strip()}'!")
                st.rerun()
            else:
                st.error(t["error_name"])

# --- TAB 5: AUTOMATED SHOPPING LIST ---
with tab5:
    st.subheader(t["shopping_header"])
    st.markdown(t["shopping_sub"])
    st.write("")

    recipes_list = get_recipes()
    recipes_by_id = {r["id"]: r for r in recipes_list}
    weekly_plan = get_weekly_plan()

    unique_ingredients = []
    seen = set()
    assigned_count = 0

    for day, meals in weekly_plan.items():
        for meal_type, recipe_id in meals.items():
            if recipe_id is not None and recipe_id in recipes_by_id:
                assigned_count += 1
                ing_text = recipes_by_id[recipe_id]["ingredients"]

                for line in ing_text.split('\n'):
                    for part in line.split(','):
                        cleaned = part.strip()
                        if cleaned and cleaned.lower() not in seen:
                            seen.add(cleaned.lower())
                            unique_ingredients.append(cleaned)

    if assigned_count == 0:
        st.info(t["no_shopping"])
    else:
        # Shareable image (PNG) styled to match the app, for sharing in chats
        list_image = generate_shopping_list_image(
            t["shopping_header"], t["tbl_no"], t["tbl_ing"], unique_ingredients
        )
        img_buffer = io.BytesIO()
        list_image.save(img_buffer, format="PNG")
        img_export = img_buffer.getvalue()

        title_col, img_col, print_col = st.columns([3.4, 1, 1])
        with title_col:
            st.markdown("### 📝 Master Deduplicated Shopping Table")
        with img_col:
            st.download_button(
                "🖼️ Image",
                data=img_export,
                file_name="shopping_list.png",
                mime="image/png",
                use_container_width=True,
            )
        with print_col:
            components.html("""
                <div style="padding-top: 8px;">
                    <button onclick="window.parent.print()" style="
                        width: 100%; background-color:#A6553C; color:#FBF8F0; border:none;
                        border-radius:8px; padding:8px 16px; font-weight:600;
                        font-family:'Kantumruy Pro', sans-serif; cursor:pointer;
                        font-size: 14px;">
                        🖨️ Print
                    </button>
                </div>
            """, height=50)

        html_table = (
            '<div id="printable-shopping-list">'
            f'<div class="print-only-title">{html.escape(t["shopping_header"])}</div>'
            '<div class="shopping-table-wrap">'
            '<table class="shopping-table">'
            '<thead>'
            '<tr>'
            f'<th>{html.escape(t["tbl_no"])}</th>'
            f'<th>{html.escape(t["tbl_ing"])}</th>'
            '</tr>'
            '</thead>'
            '<tbody>'
        )

        for idx, ing in enumerate(unique_ingredients, 1):
            html_table += (
                '<tr>'
                f'<td>{idx}</td>'
                f'<td>{html.escape(ing)}</td>'
                '</tr>'
            )

        html_table += '</tbody></table></div></div>'
        st.markdown(html_table, unsafe_allow_html=True)