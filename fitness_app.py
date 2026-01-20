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

# --- AI Logic ---
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
        # Fallback
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
    Returns common NZ brands for a food query.
    """
    prompt = (
        f"The user is searching for '{query}' in New Zealand. "
        "Identify 3-4 most common NZ brands/varieties for this. "
        "For each, give the Calories per SINGLE ITEM (if it's a wrap/cookie) OR per 100g/100ml (if it's butter/yoghurt/milk). "
        "Return ONLY a string in this format with pipe separators: "
        "'Brand Name|UnitType|Calories|CalcType(item OR gram)' "
        "Example output: "
        "'Anchor Blue Standard|100ml|63|gram\n"
        "Anchor Lite|100ml|46|gram\n"
        "Anchor Calci+|100ml|50|gram' "
        "Make sure the calorie counts are accurate for NZ products."
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
    # (Profile code omitted for brevity)
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
        st.write("### 🔎 Search & Scan")

        # --- CAMERA TOGGLE LOGIC ---
        if 'show_camera' not in st.session_state: st.session_state['show_camera'] = False
        if 'search_term' not in st.session_state: st.session_state['search_term'] = ""
        if 'brand_results' not in st.session_state: st.session_state['brand_results'] = []
        if 'selected_brand' not in st.session_state: st.session_state['selected_brand'] = None

        # Top Bar: Search Input & Camera Button
        c_search, c_cam = st.columns([4, 1])
        with c_search:
            # TEXT INPUT that triggers search on Enter
            query_input = st.text_input("Search Food (e.g. Anchor Milk)", value=st.session_state['search_term'], placeholder="Type brand or food...", label_visibility="collapsed")
        with c_cam:
            if st.button("📷", use_container_width=True):
                st.session_state['show_camera'] = not st.session_state['show_camera']
                st.rerun()

        # CAMERA ZONE (Only if toggled)
        if st.session_state['show_camera']:
            with st.container(border=True):
                col_h1, col_h2 = st.columns([4,1])
                col_h1.caption("📸 Snap a photo to identify")
                if col_h2.button("❌", key="close_cam"):
                    st.session_state['show_camera'] = False
                    st.rerun()
                
                cam_pic = st.camera_input("Scan", label_visibility="collapsed")
                if cam_pic:
                    with st.spinner("Identifying..."):
                        img = Image.open(cam_pic)
                        detected = analyze_image_for_search(img)
                        st.session_state['search_term'] = detected # Set search term
                        st.session_state['show_camera'] = False # Close cam
                        st.rerun() # Rerun to trigger search below

        # SEARCH LOGIC (Triggers if text input changes)
        if query_input and query_input != st.session_state.get('last_query', ''):
            st.session_state['last_query'] = query_input
            with st.spinner(f"Finding NZ brands for '{query_input}'..."):
                results = search_brands_nz(query_input)
                st.session_state['brand_results'] = results
                st.session_state['selected_brand'] = None # Reset selection

        # BRAND RESULTS
        if st.session_state['brand_results']:
            st.caption("👇 Select the exact match:")
            
            # Display brands as a clean radio list
            brand_opts = {f"{b['name']} ({b['cals']} cal/{b['unit']})": b for b in st.session_state['brand_results']}
            choice = st.radio("Brands", list(brand_opts.keys()), label_visibility="collapsed")
            
            # Store selection
            st.session_state['selected_brand'] = brand_opts[choice]

        # CALCULATOR (Appears when brand selected)
        if st.session_state['selected_brand']:
            brand = st.session_state['selected_brand']
            st.divider()
            
            with st.form("add_brand_form"):
                st.write(f"**Adding: {brand['name']}**")
                
                final_cals = 0
                desc = ""
                
                # Dynamic Logic: "Item" vs "Gram/ML"
                if brand['calc'] == 'item':
                    # Wraps, Cookies, Slices
                    qty = st.number_input(f"How many {brand['unit']}s?", 0.5, 10.0, 1.0, step=0.5)
                    final_cals = int(qty * brand['cals'])
                    desc = f"{qty} x {brand['name']}"
                else:
                    # Butter, Milk, Yoghurt
                    unit_label = "ml" if "ml" in brand['unit'] else "g"
                    qty = st.number_input(f"How many {unit_label}?", 0, 1000, 100 if unit_label == 'g' else 250, step=10)
                    # cals is per 100
                    final_cals = int((qty / 100) * brand['cals'])
                    desc = f"{qty}{unit_label} {brand['name']}"
                
                st.write(f"### = {final_cals} Calories")
                
                m_type = st.selectbox("Meal", ["Breakfast", "Lunch", "Dinner", "Snack"])
                save_q = st.checkbox("Save to Quick Menu")
                
                if st.form_submit_button("✅ Add Entry", type="primary"):
                    new_entry = {
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "user": user, "weight": latest_weight, 
                        "calories": final_cals, "notes": desc, "meal_type": m_type
                    }
                    updated_data = pd.concat([df_data, pd.DataFrame([new_entry])], ignore_index=True)
                    save_csv(updated_data, DATA_FILE, "Brand Add")
                    
                    if save_q:
                        new_menu = {"name": brand['name'], "cals": final_cals, "type": m_type, "desc": desc}
                        updated_menu = pd.concat([df_menu, pd.DataFrame([new_menu])], ignore_index=True)
                        save_csv(updated_menu, MENU_FILE, "Menu Update")
                    
                    st.toast("Saved!")
                    # Clear search
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
            st.info(f"Weekly Average: {int(avg_cals)} Calories")

    # --- TAB 4: SHOPPING ---
    with t_shop:
        st.write("### 🛒 Shopping List")
        for cat, items in SHOPPING_LIST.items():
            with st.expander(cat):
                for i in items:
                    st.checkbox(i, key=i)
