import streamlit as st
import streamlit.components.v1 as components
from PIL import Image
import io
import datetime
import sqlite3

# Page Configuration
st.set_page_config(
    page_title="Mom's Daily Kitchen",
    page_icon="🍲",
    layout="wide",
    initial_sidebar_state="expanded"
)

# SQLite Database Setup for Permanent Storage
def get_connection():
    return sqlite3.connect("kitchen.db", check_same_thread=False)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
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
    conn.commit()
    conn.close()

init_db()

# Database Helper Functions
def get_recipes():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, category, meat, difficulty, time, ingredients, image FROM recipes")
    rows = cursor.fetchall()
    conn.close()
    recipes = []
    for row in rows:
        recipes.append({
            "id": row[0],
            "name": row[1],
            "category": row[2],
            "meat": row[3],
            "difficulty": row[4],
            "time": row[5],
            "ingredients": row[6],
            "image": row[7]
        })
    return recipes

def add_recipe_db(name, category, meat, difficulty, time, ingredients, image):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO recipes (name, category, meat, difficulty, time, ingredients, image)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (name, category, meat, difficulty, time, ingredients, image))
    conn.commit()
    conn.close()

def update_recipe_db(recipe_id, name, category, meat, difficulty, time, ingredients, image):
    conn = get_connection()
    cursor = conn.cursor()
    if image:
        cursor.execute("""
            UPDATE recipes SET name=?, category=?, meat=?, difficulty=?, time=?, ingredients=?, image=?
            WHERE id=?
        """, (name, category, meat, difficulty, time, ingredients, image, recipe_id))
    else:
        cursor.execute("""
            UPDATE recipes SET name=?, category=?, meat=?, difficulty=?, time=?, ingredients=?
            WHERE id=?
        """, (name, category, meat, difficulty, time, ingredients, recipe_id))
    conn.commit()
    conn.close()

def delete_recipe_db(recipe_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM recipes WHERE id=?", (recipe_id,))
    conn.commit()
    conn.close()

# Professional Custom CSS Styling
st.markdown("""
    <style>
    .main {
        background-color: #f8f9fa;
    }
    h1, h2, h3 {
        color: #1e293b;
        font-family: 'Helvetica Neue', sans-serif;
    }
    .recipe-card {
        background-color: #ffffff;
        padding: 24px;
        border-radius: 16px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
        margin-bottom: 20px;
        border: 1px solid #e2e8f0;
    }
    .badge-category {
        background-color: #f3e8ff;
        color: #7e22ce;
        padding: 6px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
        display: inline-block;
        margin-right: 6px;
        margin-bottom: 4px;
    }
    .badge-meat {
        background-color: #e0f2fe;
        color: #0369a1;
        padding: 6px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
        display: inline-block;
        margin-right: 6px;
        margin-bottom: 4px;
    }
    .badge-diff-Easy {
        background-color: #dcfce7;
        color: #15803d;
        padding: 6px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
        display: inline-block;
        margin-right: 6px;
        margin-bottom: 4px;
    }
    .badge-diff-Medium {
        background-color: #fef9c3;
        color: #a16207;
        padding: 6px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
        display: inline-block;
        margin-right: 6px;
        margin-bottom: 4px;
    }
    .badge-diff-Hard {
        background-color: #fee2e2;
        color: #b91c1c;
        padding: 6px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
        display: inline-block;
        margin-right: 6px;
        margin-bottom: 4px;
    }
    .badge-time {
        background-color: #f3f4f6;
        color: #374151;
        padding: 6px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
        display: inline-block;
        margin-bottom: 4px;
    }
    </style>
""", unsafe_allow_html=True)

# Translation Dictionaries
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
        "weekly_sub": "Assign saved recipes to breakfast, lunch, and dinner for every day of the week.",
        "no_food_msg": "There's no food for that type of meat or cooking yet. Please go add some!",
        "shopping_header": "Weekly Grocery Shopping List",
        "shopping_sub": "Automatically compiled deduplicated ingredient list based on your scheduled weekly meal plan.",
        "no_shopping": "No meals scheduled in the weekly planner yet, so the shopping list is empty!",
        "save_day": "Save Plan",
        "clear_day": "Finish & Clear Day",
        "tbl_no": "No.",
        "tbl_ing": "Ingredient"
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
        "weekly_sub": "កំណត់មុខម្ហូបសម្រាប់ពេលព្រឹក ថ្ងៃត្រង់ និងល្ងាចសម្រាប់ថ្ងៃនីមួយៗក្នុងសប្តាហ៍។",
        "no_food_msg": "មិនទាន់មានម្ហូបសម្រាប់ប្រភេទសាច់ ឬប្រភេទចម្អិននេះនៅឡើយទេ សូមអញ្ជើញទៅបន្ថែម!",
        "shopping_header": "បញ្ជីទិញទំនិញផ្សារប្រចាំសប្តាហ៍",
        "shopping_sub": "បញ្ជីគ្រឿងផ្សំសរុបដែលបានចម្រាញ់រួចត្រូវបានចងក្រងដោយស្វ័យប្រវត្តិយោងតាមកាលវិភាគរបស់អ្នក។",
        "no_shopping": "មិនទាន់មានមុខម្ហូបកំណត់ក្នុងកាលវិភាគប្រចាំសប្តាហ៍នៅឡើយទេ!",
        "save_day": "រក្សាទុកចូលក្នុងបញ្ជី",
        "clear_day": "រួចរាល់ / សម្អាតថ្ងៃនេះ",
        "tbl_no": "ល.រ",
        "tbl_ing": "គ្រឿងផ្សំ"
    }
}

# Sidebar: Live Clock & Language Selection
with st.sidebar:
    components.html("""
        <div style="background: #ffffff; padding: 12px; border-radius: 12px; text-align: center; border: 1px solid #e2e8f0; box-shadow: 0 2px 5px rgba(0,0,0,0.02);">
            <p style="margin: 0; font-size: 11px; color: #64748b; font-weight: 700; letter-spacing: 0.5px;">🕒 TIME / ម៉ោង</p>
            <div id="live-clock" style="font-size: 16px; font-weight: bold; color: #1e293b; font-family: monospace; margin-top: 4px;"></div>
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

t = LANG[selected_lang]

day_display_map = {
    "Monday": "ថ្ងៃច័ន្ទ (Monday)",
    "Tuesday": "ថ្ងៃអង្គារ (Tuesday)",
    "Wednesday": "ថ្ងៃពុធ (Wednesday)",
    "Thursday": "ថ្ងៃព្រហស្បតិ៍ (Thursday)",
    "Friday": "ថ្ងៃសុក្រ (Friday)",
    "Saturday": "ថ្ងៃសៅរ៍ (Saturday)",
    "Sunday": "ថ្ងៃអាទិត្យ (Sunday)"
} if "Khmer" in selected_lang else {d: d for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]}

# Initialize weekly plan safely
if "weekly_plan" not in st.session_state:
    st.session_state.weekly_plan = {
        day: {"Breakfast": "", "Lunch": "", "Dinner": ""} 
        for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    }
else:
    for day in st.session_state.weekly_plan:
        if "Breakfast" not in st.session_state.weekly_plan[day]:
            st.session_state.weekly_plan[day]["Breakfast"] = ""

# Predefined Complete Option Lists for Categories and Meats
CATEGORY_OPTIONS = ["ប្រភេទ ឆា (Stir-Fried)", "ប្រភេទ អាំង (Grilled)", "ប្រភេទ ចៀន (Deep-Fried)", "ប្រភេទ សម្ល (Soup)", "ប្រភេទ ខ (Stew)", "ប្រភេទ ភ្លា (Salad)", "ប្រភេទ គ្រឿងសមុទ្រ (Seafood)", "ម្ហូបខ្មែរ (Khmer)", "ហូប បន្ថែម (Other)"]
MEAT_OPTIONS = ["សាច់ជ្រូក (Pork)", "សាច់មាន់ (Chicken)", "សាច់គោ (Beef)", "ត្រី / គ្រឿងសមុទ្រ (Fish / Seafood)", "បន្លែ / គ្មានសាច់ (Vegetarian / Other)"]

# App Header / Hero Section
st.title(t["title"])
st.markdown(t["subtitle"])
st.divider()

# Navigation Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([t["tab1"], t["tab2"], t["tab3"], t["tab4"], t["tab5"]])

# --- TAB 1: TODAY'S MENU (MAIN HOME TAB) ---
with tab1:
    st.subheader(t["tab1"])
    
    today_name = datetime.date.today().strftime("%A")
    days_list = list(st.session_state.weekly_plan.keys())
    default_index = days_list.index(today_name) if today_name in days_list else 0
    
    selected_view_day = st.selectbox(
        t["view_for"], 
        days_list, 
        index=default_index, 
        format_func=lambda x: day_display_map[x]
    )
    
    st.markdown(f"### 🍽️ {day_display_map[selected_view_day]}")
    st.write("")
    
    day_meals = st.session_state.weekly_plan.get(selected_view_day, {})
    recipes_list = get_recipes()
    
    def render_today_meal(meal_type_label, meal_key):
        recipe_name = day_meals.get(meal_key, "")
        st.markdown(f"#### ⏰ {meal_type_label}")
        if recipe_name:
            recipe = next((r for r in recipes_list if r["name"] == recipe_name), None)
            if recipe:
                st.markdown('<div class="recipe-card">', unsafe_allow_html=True)
                rc_col1, rc_col2 = st.columns([1, 3])
                
                with rc_col1:
                    if recipe["image"]:
                        img = Image.open(io.BytesIO(recipe["image"]))
                        st.image(img, use_container_width=True)
                    else:
                        st.markdown(f"🖼️ *{t['no_image']}*")
                        
                with rc_col2:
                    st.markdown(f"### {recipe['name']}")
                    cat_badge = f'<span class="badge-category">🍳 {recipe.get("category", "General")}</span>'
                    
                    meat_vals = [m.strip() for m in recipe["meat"].split(",") if m.strip()]
                    meat_badges = "".join([f'<span class="badge-meat">🥩 {m}</span>' for m in meat_vals])
                    
                    diff_badge = f'<span class="badge-diff-{recipe["difficulty"]}">⚡ {recipe["difficulty"]}</span>'
                    time_badge = f'<span class="badge-time">⏱️ {recipe["time"]}</span>'
                    st.markdown(f"{cat_badge} {meat_badges} {diff_badge} {time_badge}", unsafe_allow_html=True)
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.markdown(f"**{t['ingredients']}:**\n{recipe['ingredients']}")
                    
                st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.info(f"Recipe '{recipe_name}' was removed.")
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
    recipe_names = [""] + [r["name"] for r in recipes_list]
    col_days = st.columns(2)
    days = list(st.session_state.weekly_plan.keys())
    
    for idx, day in enumerate(days):
        b_key = f"breakfast_{day}"
        l_key = f"lunch_{day}"
        d_key = f"dinner_{day}"

        with col_days[idx % 2]:
            with st.container():
                st.markdown(f"### 🗓️ {day_display_map[day]}")
                
                # Action Buttons placed ABOVE the selectboxes so they clear instantly in 1 click
                btn_col1, btn_col2 = st.columns(2)
                with btn_col1:
                    if st.button(f"💾 {t['save_day']}", key=f"save_btn_{day}"):
                        st.success(f"{day_display_map[day]} added to menu plan!")
                with btn_col2:
                    if st.button(f"🧹 {t['clear_day']}", key=f"clear_btn_{day}"):
                        st.session_state[b_key] = ""
                        st.session_state[l_key] = ""
                        st.session_state[d_key] = ""
                        st.session_state.weekly_plan[day]["Breakfast"] = ""
                        st.session_state.weekly_plan[day]["Lunch"] = ""
                        st.session_state.weekly_plan[day]["Dinner"] = ""
                        st.success(f"Cleared {day_display_map[day]}! Ready for new meals.")
                        st.rerun()

                if b_key not in st.session_state:
                    st.session_state[b_key] = st.session_state.weekly_plan[day].get("Breakfast", "")
                if l_key not in st.session_state:
                    st.session_state[l_key] = st.session_state.weekly_plan[day].get("Lunch", "")
                if d_key not in st.session_state:
                    st.session_state[d_key] = st.session_state.weekly_plan[day].get("Dinner", "")

                breakfast_choice = st.selectbox(
                    f"{t['breakfast']} ({day_display_map[day]})", 
                    recipe_names, 
                    key=b_key
                )
                lunch_choice = st.selectbox(
                    f"{t['lunch']} ({day_display_map[day]})", 
                    recipe_names, 
                    key=l_key
                )
                dinner_choice = st.selectbox(
                    f"{t['dinner']} ({day_display_map[day]})", 
                    recipe_names, 
                    key=d_key
                )
                
                st.session_state.weekly_plan[day]["Breakfast"] = breakfast_choice
                st.session_state.weekly_plan[day]["Lunch"] = lunch_choice
                st.session_state.weekly_plan[day]["Dinner"] = dinner_choice
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
            for recipe in filtered:
                recipe_id = recipe["id"]
                with st.container():
                    st.markdown('<div class="recipe-card">', unsafe_allow_html=True)
                    rc_col1, rc_col2 = st.columns([1, 3])
                    
                    with rc_col1:
                        if recipe["image"]:
                            img = Image.open(io.BytesIO(recipe["image"]))
                            st.image(img, use_container_width=True)
                        else:
                            st.markdown(f"🖼️ *{t['no_image']}*")
                            
                    with rc_col2:
                        st.markdown(f"### {recipe['name']}")
                        
                        cat_badge = f'<span class="badge-category">🍳 {recipe.get("category", "General")}</span>'
                        
                        meat_vals = [m.strip() for m in recipe["meat"].split(",") if m.strip()]
                        meat_badges = "".join([f'<span class="badge-meat">🥩 {m}</span>' for m in meat_vals])
                        
                        diff_badge = f'<span class="badge-diff-{recipe["difficulty"]}">⚡ {recipe["difficulty"]}</span>'
                        time_badge = f'<span class="badge-time">⏱️ {recipe["time"]}</span>'
                        st.markdown(f"{cat_badge} {meat_badges} {diff_badge} {time_badge}", unsafe_allow_html=True)
                        
                        st.markdown("<br>", unsafe_allow_html=True)
                        st.markdown(f"**{t['ingredients']}:**\n{recipe['ingredients']}")
                        
                        # EDIT EXPANDER FOR EACH RECIPE
                        with st.expander("✏️ Edit Recipe Details"):
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
                                    img_bytes = new_image.read() if new_image else None
                                    meat_str = ", ".join(new_meats) if new_meats else "None"
                                    update_recipe_db(recipe_id, new_name, new_cat, meat_str, new_diff, new_time, new_ingredients, img_bytes)
                                    st.success("Recipe updated successfully!")
                                    st.rerun()

                        if st.button("🗑️ Delete Recipe", key=f"del_{recipe_id}"):
                            delete_recipe_db(recipe_id)
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
            if dish_name:
                img_bytes = image_file.read() if image_file else None
                meat_str = ", ".join(meat_types) if meat_types else "None"
                add_recipe_db(dish_name, cat_type, meat_str, difficulty, prep_time if prep_time else "Quick", ingredients if ingredients else "Not specified", img_bytes)
                st.success(f"{t['success_add']} '{dish_name}'!")
                st.rerun()
            else:
                st.error(t["error_name"])

# --- TAB 5: AUTOMATED SHOPPING LIST ---
with tab5:
    st.subheader(t["shopping_header"])
    st.markdown(t["shopping_sub"])
    st.write("")
    
    recipes_list = get_recipes()
    recipe_dict = {r["name"]: r for r in recipes_list}
    
    unique_ingredients = []
    seen = set()
    assigned_count = 0
    
    for day, meals in st.session_state.weekly_plan.items():
        for meal_type, r_name in meals.items():
            if r_name and r_name in recipe_dict:
                assigned_count += 1
                ing_text = recipe_dict[r_name]["ingredients"]
                
                for line in ing_text.split('\n'):
                    for part in line.split(','):
                        cleaned = part.strip()
                        if cleaned and cleaned not in seen:
                            seen.add(cleaned)
                            unique_ingredients.append(cleaned)
                
    if assigned_count == 0:
        st.info(t["no_shopping"])
    else:
        st.markdown("### 📝 Master Deduplicated Shopping Table")
        
        html_table = (
            '<table style="width:100%; border-collapse: collapse; background-color: #ffffff; border: 1px solid #e2e8f0; font-family: sans-serif; border-radius: 8px; overflow: hidden;">'
            '<thead>'
            '<tr style="background-color: #f8f9fa; border-bottom: 2px solid #e2e8f0;">'
            f'<th style="padding: 14px; text-align: center; width: 10%; color: #1e293b; font-weight: bold; border-right: 1px solid #e2e8f0;">{t["tbl_no"]}</th>'
            f'<th style="padding: 14px; text-align: left; width: 90%; color: #1e293b; font-weight: bold; padding-left: 20px;">{t["tbl_ing"]}</th>'
            '</tr>'
            '</thead>'
            '<tbody>'
        )
        
        for idx, ing in enumerate(unique_ingredients, 1):
            html_table += (
                '<tr style="border-bottom: 1px solid #e2e8f0;">'
                f'<td style="padding: 12px; text-align: center; color: #334155; font-weight: 600; border-right: 1px solid #e2e8f0;">{idx}</td>'
                f'<td style="padding: 12px; text-align: left; color: #334155; padding-left: 20px;">{ing}</td>'
                '</tr>'
            )
            
        html_table += '</tbody></table>'
        st.markdown(html_table, unsafe_allow_html=True)