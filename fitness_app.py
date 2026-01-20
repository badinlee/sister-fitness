import streamlit as st
import pandas as pd
from datetime import datetime, date, time, timedelta
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

# --- DATA ---
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

# --- ADVANCED AI LOGIC ---
def get_ai_response(prompt, image=None):
    try:
        if image:
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content([prompt, image])
        else:
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt)
        return response.text
    except:
        try:
            if image:
                model = genai.GenerativeModel('gemini-pro-vision')
                response = model.generate_content([prompt, image])
            else:
                model = genai.GenerativeModel('gemini-pro')
                response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"Error: {str(e)}"

def search_brands_nz(query):
    """
    Asks AI to return 3 common NZ brands for a generic food.
    Returns a list of dicts: [{'brand': 'Farrahs', 'unit': 'Wrap', 'cals': 180, 'type': 'item'}, ...]
    """
    prompt = (
        f"The user is searching for '{query}' in New Zealand. "
        "Identify 3-4 most common NZ brands/varieties for this. "
        "For each, give the Calories per SINGLE ITEM (if it's a wrap/cookie) OR per 100g (if it's butter/yoghurt). "
        "Return ONLY a string in this format with pipe separators: "
        "'Brand Name|UnitType(e.g. 1 Wrap or 100g)|Calories|CalcType(item OR gram)' "
        "Example output: "
        "'Farrahs Garlic|1 Wrap|216|item\n"
        "Rebel Spinach|1 Wrap|134|item\n"
        "Giannis|1 Wrap|180|item' "
        "If the food is generic (like Apple), just return one line: 'Generic Apple|1 Medium|80|item'."
    )
    res = get_ai_response(prompt).strip()
    
    brands = []
    lines = res.split('\n')
    for line in lines:
        if '|' in line:
            parts = line.split('|')
            if len(parts) >= 4:
                brands.append({
                    "name": parts[0].strip(),
                    "unit": parts[1].strip(),
                    "cals": int(''.join(filter(str.isdigit, parts[2]))),
                    "calc": parts[3].strip().lower()
                })
    return brands

def analyze_image_for_search(image):
    """Just identifies the food name from image so we can search brands."""
    prompt = "Identify this food item. Return ONLY the generic name (e.g. 'Garlic Wrap' or 'Strawberry Yoghurt')."
    return get_ai_response(prompt, image).strip()

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
    # (Profile creation hidden for brevity)
else:
    user_profile = user_profile_data.iloc[0]
    
    # Dates
    today_obj = datetime.now()
    today_str_nz = today_obj.strftime("%d/%m/%Y")
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
        # QUICK BUTTONS
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
        
        # --- STATE MANAGEMENT ---
        if 'show_camera' not in st.session_state: st.session_state['show_camera'] = False
        if 'search_results' not in st.session_state: st.session_state['search_results'] = []
        if 'selected_food' not in st.session_state: st.session_state['selected_food'] = None

        # 1. SEARCH INPUTS
        col_txt, col_cam = st.columns([4, 1])
        with col_txt:
            search_query = st.text_input("Type Food (e.g. Garlic Wrap)", key="search_box", label_visibility="collapsed", placeholder="Type food...")
        with col_cam:
            if st.button("📷"):
                st.session_state['show_camera'] = True

        # 2. CAMERA FRAME (Conditional)
        if st.session_state['show_camera']:
            with st.container(border=True):
                col_x1, col_x2 = st.columns([4, 1])
                col_x1.write("📸 Snap Photo")
                if col_x2.button("❌"):
                    st.session_state['show_camera'] = False
                    st.rerun()
                
                cam_img = st.camera_input("Scan Food")
                if cam_img:
                    with st.spinner("Identifying..."):
                        img = Image.open(cam_img)
                        detected_name = analyze_image_for_search(img)
                        # Auto-trigger search with detected name
                        st.session_state['show_camera'] = False # Close camera
                        search_query = detected_name # Pass to search
                        # We force the search logic below to run by simulating a submit
                        st.session_state['force_search'] = detected_name

        # 3. PERFORM SEARCH (Text or AI Detected)
        trigger_search = False
        if search_query: trigger_search = True
        if 'force_search' in st.session_state:
            search_query = st.session_state['force_search']
            trigger_search = True
            del st.session_state['force_search']

        if trigger_search:
            # Only search if we haven't already results for this query
            # (Simple check to prevent re-running on every refresh)
            if st.button("Find Brands") or trigger_search: 
                with st.spinner(f"Looking up NZ brands for '{search_query}'..."):
                    results = search_brands_nz(search_query)
                    st.session_state['search_results'] = results
                    st.session_state['selected_food'] = None # Reset selection

        # 4. SHOW RESULTS (Radio Buttons)
        if st.session_state['search_results']:
            st.write("Select Brand:")
            
            # Format options for display
            options = {f"{r['name']} ({r['cals']} cal per {r['unit']})": r for r in st.session_state['search_results']}
            selection = st.radio("Pick one:", list(options.keys()))
            
            # Store selection
            st.session_state['selected_food'] = options[selection]

        # 5. CALCULATOR (Based on Brand Selection)
        if st.session_state['selected_food']:
            food_data = st.session_state['selected_food']
            st.divider()
            st.write(f"**Track: {food_data['name']}**")
            
            with st.form("track_brand"):
                final_cals = 0
                qty_desc = ""
                
                if food_data['calc'] == 'item':
                    # It's a wrap/cookie/slice
                    qty = st.number_input(f"How many {food_data['unit']}s?", 0.5, 10.0, 1.0, step=0.5)
                    final_cals = int(qty * food_data['cals'])
                    qty_desc = f"{qty} x {food_data['name']}"
                else:
                    # It's gram based (butter/yogurt)
                    grams = st.number_input("How many grams?", 0, 500, 100, step=10)
                    # cals is per 100g
                    final_cals = int((grams / 100) * food_data['cals'])
                    qty_desc = f"{grams}g {food_data['name']}"
                
                st.write(f"### Total: {final_cals} Calories")
                
                m_type = st.selectbox("Meal", ["Breakfast", "Lunch", "Dinner", "Snack"])
                save_q = st.checkbox("Save to Quick Menu")
                
                if st.form_submit_button("✅ Add to Diary", type="primary"):
                    new_entry = {
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "user": user, "weight": latest_weight, 
                        "calories": final_cals, "notes": qty_desc, "meal_type": m_type
                    }
                    updated_data = pd.concat([df_data, pd.DataFrame([new_entry])], ignore_index=True)
                    save_csv(updated_data, DATA_FILE, "Brand Add")
                    
                    if save_q:
                        new_menu = {"name": food_data['name'], "cals": final_cals, "type": m_type, "desc": qty_desc}
                        updated_menu = pd.concat([df_menu, pd.DataFrame([new_menu])], ignore_index=True)
                        save_csv(updated_menu, MENU_FILE, "Menu Update")
                    
                    # Cleanup
                    st.session_state['search_results'] = []
                    st.session_state['selected_food'] = None
                    st.toast("Saved!")
                    time_lib.sleep(0.5)
                    st.rerun()

    # --- TAB 2: CLEAN DIARY & EDITOR ---
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
                md1.metric("Calories Used", int(d_total))
                md2.metric("Remaining", int(d_rem), delta_color="normal" if d_rem > 0 else "inverse")
                st.progress(min(1.0, d_total / goal) if goal > 0 else 0)
                
            st.divider()
            if not day_data.empty:
                st.info("💡 Edit numbers below and click Update")
                edited_day = st.data_editor(
                    day_data[["meal_type", "notes", "calories"]],
                    column_config={
                        "meal_type": st.column_config.SelectboxColumn("Meal", options=["Breakfast", "Lunch", "Dinner", "Snack"], width="small"),
                        "notes": st.column_config.TextColumn("Food Item", width="large"),
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
                    
                    new_day_df = pd.DataFrame(new_rows)
                    final_df = pd.concat([data_to_keep, new_day_df], ignore_index=True)
                    save_csv(final_df, DATA_FILE, f"Updated {sel_date_iso}")
                    st.toast("✅ Diary Updated!")
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
            avg_cals = user_history.groupby("iso_date")["calories"].sum().mean()
            diff = goal - avg_cals
            if diff > 300: st.info(f"Week Avg: {int(avg_cals)}. Under-eating by {int(diff)}.")
            elif diff < -100: st.warning(f"Week Avg: {int(avg_cals)}. Slightly over goal.")
            else: st.success("🎉 On track!")

    # --- TAB 4: SHOPPING ---
    with t_shop:
        st.write("### 🛒 Shopping List")
        for cat, items in SHOPPING_LIST.items():
            with st.expander(cat):
                for i in items:
                    st.checkbox(i, key=i)
