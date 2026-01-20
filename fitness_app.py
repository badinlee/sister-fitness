import streamlit as st
import pandas as pd
from datetime import datetime, date, time
from github import Github
import io
import plotly.express as px
import google.generativeai as genai
from PIL import Image
import time as time_lib

# --- Configuration ---
REPO_NAME = "badinlee/sister-fitness"  # <--- UPDATE THIS
DATA_FILE = "data.csv"
PROFILE_FILE = "profiles.csv"
MENU_FILE = "my_menu.csv"

# --- 1. THE "OFFLINE BRAIN" (NZ Database) ---
# This works 100% of the time, even if AI fails.
LOCAL_NZ_DB = {
    "anchor": [
        {"name": "Anchor Blue Milk (Standard)", "unit": "100ml", "cals": 63, "calc": "gram"},
        {"name": "Anchor Lite Milk (Light Blue)", "unit": "100ml", "cals": 46, "calc": "gram"},
        {"name": "Anchor Trim Milk (Green)", "unit": "100ml", "cals": 35, "calc": "gram"},
        {"name": "Anchor Protein+ Yoghurt", "unit": "100g", "cals": 58, "calc": "gram"},
        {"name": "Anchor Butter", "unit": "10g", "cals": 74, "calc": "gram"}
    ],
    "watties": [
        {"name": "Watties Baked Beans", "unit": "100g", "cals": 90, "calc": "gram"},
        {"name": "Watties Spaghetti", "unit": "100g", "cals": 75, "calc": "gram"},
        {"name": "Watties SteamFresh Veg", "unit": "100g", "cals": 50, "calc": "gram"}
    ],
    "farrah": [
        {"name": "Farrah's White Wrap", "unit": "1 Wrap", "cals": 202, "calc": "item"},
        {"name": "Farrah's Spinach Wrap", "unit": "1 Wrap", "cals": 198, "calc": "item"},
        {"name": "Farrah's Garlic Butter Wrap", "unit": "1 Wrap", "cals": 216, "calc": "item"},
        {"name": "Farrah's Low Carb Wrap", "unit": "1 Wrap", "cals": 136, "calc": "item"}
    ],
    "vogel": [
        {"name": "Vogel's Mixed Grain (Thin)", "unit": "1 Slice", "cals": 86, "calc": "item"},
        {"name": "Vogel's Mixed Grain (Toast)", "unit": "1 Slice", "cals": 115, "calc": "item"},
        {"name": "Vogel's Sunflower & Barley", "unit": "1 Slice", "cals": 118, "calc": "item"}
    ],
    "rebel": [
        {"name": "Rebel Bagel Thin (Original)", "unit": "1 Bagel", "cals": 140, "calc": "item"},
        {"name": "Rebel Bagel Thin (Low Carb)", "unit": "1 Bagel", "cals": 110, "calc": "item"}
    ],
    "egg": [
        {"name": "Egg (Large, Boiled/Poached)", "unit": "1 Egg", "cals": 74, "calc": "item"},
        {"name": "Egg (Fried in Oil)", "unit": "1 Egg", "cals": 90, "calc": "item"}
    ],
    "banana": [{"name": "Banana (Medium)", "unit": "1 Item", "cals": 105, "calc": "item"}],
    "apple": [{"name": "Apple (Medium)", "unit": "1 Item", "cals": 80, "calc": "item"}],
    "avocado": [{"name": "Avocado (Half)", "unit": "0.5 Avo", "cals": 130, "calc": "item"}]
}

# --- DATA & CONFIG ---
SHOPPING_LIST = {
    "Produce": ["Spinach/Salad Mix", "Frozen Mixed Berries (Large)", "Avocados (3-4)", "Fruit (10 pieces)", "Frozen Veg (4 bags)", "Courgettes", "Garlic & Ginger"],
    "Butchery": ["Chicken Breast (3kg)", "Eggs (1 Dozen)", "Anchor Protein+ Yogurt (2kg)", "Cheese (500g Edam/Tasty)"],
    "Pantry": ["Vogel's Bread", "Bagel Thins (Rebel)", "Rice Cups (6-8) or 1kg Bag", "Salsa (F. Whitlock's)", "Oil Spray", "Mayo/Soy/Honey/Sriracha", "Spices (Paprika, Garlic, Cajun)"]
}

BASE_MENU = [
    {"name": "Breakfast (Standard)", "cals": 400, "type": "Breakfast", "desc": "220g Yogurt + 100g Berries + 25g Nuts"},
    {"name": "Breakfast (Toast)", "cals": 400, "type": "Breakfast", "desc": "2 Vogel's + 75g Avo + 1 Egg"},
    {"name": "Snack (Bridge)", "cals": 250, "type": "Snack", "desc": "Fruit + Protein Shake/Coffee"},
    {"name": "Dinner A (Stir-Fry)", "cals": 1000, "type": "Dinner", "desc": "Honey Soy Chicken + Rice + Veg"},
    {"name": "Dinner B (Burger)", "cals": 1000, "type": "Dinner", "desc": "Double Chicken Burger + Wedges"},
    {"name": "Dinner C (Mexican)", "cals": 1000, "type": "Dinner", "desc": "Mexican Bowl + Avo"}
]

# --- Setup Google AI ---
if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])

# --- GitHub Functions ---
def get_repo():
    g = Github(st.secrets["GITHUB_TOKEN"])
    return g.get_repo(REPO_NAME)

def load_csv(filename):
    try:
        repo = get_repo()
        contents = repo.get_contents(filename)
        df = pd.read_csv(io.StringIO(contents.decoded_content.decode()))
        return df
    except:
        return pd.DataFrame()

def save_csv(df, filename, message):
    repo = get_repo()
    csv_content = df.to_csv(index=False)
    try:
        contents = repo.get_contents(filename)
        repo.update_file(contents.path, message, csv_content, contents.sha)
    except:
        repo.create_file(filename, message, csv_content)

# --- HYBRID SEARCH ENGINE (Local + AI) ---
def get_ai_response(prompt):
    """Attempt AI, fail gracefully."""
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        return response.text
    except:
        try:
            model = genai.GenerativeModel('gemini-pro')
            response = model.generate_content(prompt)
            return response.text
        except:
            return "Error"

def search_brands_hybrid(query):
    """Checks Local DB first. If not found, tries AI."""
    query_lower = query.lower()
    results = []

    # 1. Check Local DB
    for key in LOCAL_NZ_DB:
        if key in query_lower:
            results.extend(LOCAL_NZ_DB[key])
    
    # 2. If we found local results, return them immediately (Fast!)
    if results:
        return results

    # 3. If not found, Ask AI (Backup)
    prompt = (
        f"The user is searching for '{query}' in New Zealand. "
        "Identify 3-4 common brands. "
        "Return ONLY a string in this format: 'Brand Name|UnitType|Calories|CalcType(item OR gram)' "
        "Example: 'Generic|100g|50|gram'. "
    )
    res = get_ai_response(prompt).strip()
    
    if res and "Error" not in res:
        lines = res.split('\n')
        for line in lines:
            if '|' in line:
                parts = line.split('|')
                if len(parts) >= 4:
                    results.append({
                        "name": parts[0].strip(),
                        "unit": parts[1].strip(),
                        "cals": int(''.join(filter(str.isdigit, parts[2]))),
                        "calc": parts[3].strip().lower()
                    })
    
    return results

def analyze_image_for_search(image):
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        res = model.generate_content(["Identify this food item name only.", image])
        return res.text.strip()
    except:
        return "Unknown Food"

# --- App Layout ---
st.set_page_config(page_title="SisFit", page_icon="🦋", layout="centered", initial_sidebar_state="collapsed")

# Header
c1, c2 = st.columns([3, 1])
with c1: st.title("🦋 SisFit")
with c2: user = st.selectbox("User", ["Me", "Sister"], label_visibility="collapsed")

# Load Data
df_data = load_csv(DATA_FILE)
df_profiles = load_csv(PROFILE_FILE)
df_menu = load_csv(MENU_FILE)
full_menu = BASE_MENU.copy()
if not df_menu.empty:
    for index, row in df_menu.iterrows():
        full_menu.append(row.to_dict())

# Repair
if not df_data.empty:
    for col in ["meal_type", "notes"]:
        if col not in df_data.columns: df_data[col] = ""
    if "calories" not in df_data.columns: df_data["calories"] = 0
    if "weight" not in df_data.columns: df_data["weight"] = 0.0

# Profile Check
user_profile_data = df_profiles[df_profiles["user"] == user] if not df_profiles.empty else pd.DataFrame()
if user_profile_data.empty:
    st.info("Please create a profile.")
    with st.form("create_profile"):
        h = st.number_input("Height (m)", 1.0, 2.5, 1.65)
        sw = st.number_input("Starting Weight (kg)", 40.0, 200.0, 70.0)
        gw = st.number_input("Goal Weight (kg)", 40.0, 200.0, 60.0)
        ct = st.number_input("Daily Calories", 1000, 4000, 1650)
        if st.form_submit_button("Start Journey"):
            new_prof = {"user": user, "height": h, "start_weight": sw, "goal_weight": gw, "calorie_target": ct}
            updated_profs = pd.concat([df_profiles, pd.DataFrame([new_prof])], ignore_index=True)
            save_csv(updated_profs, PROFILE_FILE, "Created profile")
            st.rerun()
else:
    user_profile = user_profile_data.iloc[0]
    
    # Dates
    today_obj = datetime.now()
    today_str_iso = today_obj.strftime("%Y-%m-%d")
    
    calories_today = 0
    latest_weight = user_profile["start_weight"]
    
    user_history = df_data[df_data["user"] == user].copy() if not df_data.empty else pd.DataFrame()
    if not user_history.empty:
        user_history["dt"] = pd.to_datetime(user_history["date"])
        user_history["nice_date"] = user_history["dt"].dt.strftime("%a %d %b")
        user_history["iso_date"] = user_history["dt"].dt.strftime("%Y-%m-%d")
        
        todays_logs = user_history[user_history["iso_date"] == today_str_iso]
        calories_today = todays_logs["calories"].sum()
        latest_weight = user_history.iloc[-1]['weight']
    
    goal = int(user_profile["calorie_target"])
    
    # Hero Stats
    st.markdown("---")
    m1, m2, m3 = st.columns(3)
    m1.metric("Today", int(calories_today))
    rem_today = goal - int(calories_today)
    m2.metric("Left", rem_today, delta_color="normal" if rem_today > 0 else "inverse")
    m3.metric("Kg", f"{latest_weight}")
    
    # Tabs
    t_add, t_diary, t_trends, t_shop = st.tabs(["➕ Log Food", "📅 Diary", "📊 Trends", "🛒 List"])

    # --- TAB 1: LOGGING ---
    with t_add:
        # QUICK MENU
        with st.expander("⚡ Quick Menu", expanded=False):
            g1, g2 = st.columns(2)
            for i, item in enumerate(full_menu):
                with (g1 if i % 2 == 0 else g2):
                    if st.button(f"{item['name']} ({item['cals']})", key=f"q_{i}", use_container_width=True):
                        new_entry = {
                            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "user": user, "weight": latest_weight, 
                            "calories": item['cals'], "notes": item['desc'], "meal_type": item['type']
                        }
                        updated_data = pd.concat([df_data, pd.DataFrame([new_entry])], ignore_index=True)
                        save_csv(updated_data, DATA_FILE, "Quick Add")
                        st.toast(f"✅ Added {item['name']}!")
                        time_lib.sleep(0.5)
                        st.rerun()

        st.divider()
        st.write("### 🔎 Search NZ Brands")

        # --- STATE ---
        if 'show_camera' not in st.session_state: st.session_state['show_camera'] = False
        if 'search_term' not in st.session_state: st.session_state['search_term'] = ""
        if 'brand_results' not in st.session_state: st.session_state['brand_results'] = []
        if 'selected_brand' not in st.session_state: st.session_state['selected_brand'] = None

        # SEARCH BAR
        c_search, c_btn, c_cam = st.columns([3, 1, 1])
        with c_search:
            query_input = st.text_input("Search", value=st.session_state['search_term'], placeholder="e.g. Anchor Milk", label_visibility="collapsed")
        with c_btn:
            if st.button("🔍 Find"):
                st.session_state['search_term'] = query_input
                # FORCE SEARCH
                with st.spinner("Searching..."):
                    results = search_brands_hybrid(query_input)
                    st.session_state['brand_results'] = results
                    st.session_state['selected_brand'] = None
        with c_cam:
            if st.button("📷"):
                st.session_state['show_camera'] = not st.session_state['show_camera']
                st.rerun()

        # CAMERA
        if st.session_state['show_camera']:
            with st.container(border=True):
                col_h1, col_h2 = st.columns([4,1])
                col_h1.caption("📸 Scan Food")
                if col_h2.button("❌"):
                    st.session_state['show_camera'] = False
                    st.rerun()
                cam_pic = st.camera_input("Scan", label_visibility="collapsed")
                if cam_pic:
                    with st.spinner("Identifying..."):
                        img = Image.open(cam_pic)
                        detected = analyze_image_for_search(img)
                        st.session_state['search_term'] = detected
                        st.session_state['show_camera'] = False
                        # Auto Search
                        results = search_brands_hybrid(detected)
                        st.session_state['brand_results'] = results
                        st.rerun()

        # RESULTS
        if st.session_state['brand_results']:
            st.caption("👇 Select exact match:")
            brand_opts = {f"{b['name']} ({b['cals']} cal/{b['unit']})": b for b in st.session_state['brand_results']}
            choice = st.radio("Brands", list(brand_opts.keys()), label_visibility="collapsed")
            st.session_state['selected_brand'] = brand_opts[choice]

        # CALCULATOR
        if st.session_state['selected_brand']:
            brand = st.session_state['selected_brand']
            st.divider()
            
            with st.form("add_brand_form"):
                st.write(f"**Adding: {brand['name']}**")
                
                final_cals = 0
                desc = ""
                
                if brand['calc'] == 'item':
                    qty = st.number_input(f"How many {brand['unit']}s?", 0.5, 10.0, 1.0, step=0.5)
                    final_cals = int(qty * brand['cals'])
                    desc = f"{qty} x {brand['name']}"
                else:
                    unit_label = "ml" if "ml" in brand['unit'] else "g"
                    qty = st.number_input(f"How many {unit_label}?", 0, 1000, 100 if unit_label == 'g' else 250, step=10)
                    final_cals = int((qty / 100) * brand['cals'])
                    desc = f"{qty}{unit_label} {brand['name']}"
                
                st.write(f"### = {final_cals} Calories")
                m_type = st.selectbox("Meal", ["Breakfast", "Lunch", "Dinner", "Snack"])
                
                if st.form_submit_button("✅ Add Entry", type="primary"):
                    new_entry = {
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "user": user, "weight": latest_weight, 
                        "calories": final_cals, "notes": desc, "meal_type": m_type
                    }
                    updated_data = pd.concat([df_data, pd.DataFrame([new_entry])], ignore_index=True)
                    save_csv(updated_data, DATA_FILE, "Brand Add")
                    
                    st.toast("Saved!")
                    st.session_state['search_term'] = ""
                    st.session_state['brand_results'] = []
                    st.session_state['selected_brand'] = None
                    time_lib.sleep(0.5)
                    st.rerun()

    # --- TAB 2: CLEAN DIARY ---
    with t_diary:
        st.subheader("📅 Daily Journal")
        col_d1, col_d2 = st.columns([2, 1])
        with col_d1: sel_date = st.date_input("View Date", value=datetime.now())
        sel_date_iso = sel_date.strftime("%Y-%m-%d")
        sel_display = sel_date.strftime("%A %d %B")
        
        if not user_history.empty:
            day_data = user_history[user_history["iso_date"] == sel_date_iso]
            with st.container(border=True):
                st.markdown(f"### {sel_display}")
                d_total = day_data["calories"].sum() if not day_data.empty else 0
                d_rem = goal - d_total
                md1, md2 = st.columns(2)
                md1.metric("Used", int(d_total))
                md2.metric("Left", int(d_rem), delta_color="normal" if d_rem > 0 else "inverse")
                st.progress(min(1.0, d_total / goal) if goal > 0 else 0)
            
            st.divider()
            if not day_data.empty:
                st.info("💡 Edit numbers below and click Update")
                edited_day = st.data_editor(
                    day_data[["meal_type", "notes", "calories"]],
                    column_config={
                        "meal_type": st.column_config.SelectboxColumn("Meal", options=["Breakfast", "Lunch", "Dinner", "Snack"], width="small"),
                        "notes": st.column_config.TextColumn("Food", width="large"),
                        "calories": st.column_config.NumberColumn("Cals", width="small")
                    },
                    use_container_width=True, num_rows="dynamic", key="day_editor"
                )
                if st.button(f"🔄 Update Diary", type="primary"):
                    full_df = load_csv(DATA_FILE)
                    full_df["temp_dt"] = pd.to_datetime(full_df["date"])
                    full_df["temp_iso"] = full_df["temp_dt"].dt.strftime("%Y-%m-%d")
                    keep_mask = ~((full_df["user"] == user) & (full_df["temp_iso"] == sel_date_iso))
                    data_to_keep = full_df[keep_mask].drop(columns=["temp_dt", "temp_iso"])
                    
                    base_ts = day_data.iloc[0]["date"]
                    base_w = day_data.iloc[0]["weight"]
                    new_rows = []
                    for idx, row in edited_day.iterrows():
                        new_rows.append({"date": base_ts, "user": user, "weight": base_w, "calories": row["calories"], "notes": row["notes"], "meal_type": row["meal_type"]})
                    
                    final_df = pd.concat([data_to_keep, pd.DataFrame(new_rows)], ignore_index=True)
                    save_csv(final_df, DATA_FILE, f"Updated {sel_date_iso}")
                    st.toast("✅ Updated!")
                    time_lib.sleep(1)
                    st.rerun()
            else:
                st.write("No meals logged.")
        else:
            st.write("No history.")

    # --- TAB 3: TRENDS ---
    with t_trends:
        st.subheader("📊 Trends")
        if not user_history.empty:
            fig = px.line(user_history, x="dt", y="weight", markers=True, title="Weight Progress")
            st.plotly_chart(fig, use_container_width=True)
            
            all_users = df_data["user"].unique()
            if len(all_users) > 1:
                st.write("### 🏆 Leaderboard")
                scores = []
                for u in all_users:
                    u_hist = df_data[df_data["user"] == u]
                    if not u_hist.empty:
                        loss = u_hist.iloc[0]["weight"] - u_hist.iloc[-1]["weight"]
                        scores.append({"User": u, "Kg Lost": f"{loss:.1f}"})
                st.dataframe(pd.DataFrame(scores), hide_index=True)

    # --- TAB 4: SHOPPING ---
    with t_shop:
        st.write("### 🛒 Shopping List")
        for cat, items in SHOPPING_LIST.items():
            with st.expander(cat):
                for i in items:
                    st.checkbox(i, key=i)
