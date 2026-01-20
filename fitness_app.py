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

# --- YOUR DATA ---
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

# --- ROBUST AI LOGIC (The Fix!) ---
def get_ai_response(prompt, image=None):
    """Tries the new model, falls back to old model if it crashes."""
    
    # 1. Try the new fast model (Gemini 1.5)
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        if image:
            response = model.generate_content([prompt, image])
        else:
            response = model.generate_content(prompt)
        return response.text
    except:
        # 2. If that fails (404 Error), use the 'Classic' models
        try:
            if image:
                model = genai.GenerativeModel('gemini-pro-vision') # Classic Vision
                response = model.generate_content([prompt, image])
            else:
                model = genai.GenerativeModel('gemini-pro') # Classic Text
                response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"Error: {str(e)}"

def analyze_image(image_data):
    prompt = (
        "Analyze this image. It might be food, a barcode, or a nutrition label. "
        "Return ONLY a string: 'Food Name|Calories'. Example: 'Oat Bar|180'. "
        "If unknown, return 'Unknown|0'."
    )
    text = get_ai_response(prompt, image_data).strip()
    if '|' in text:
        name, cals = text.split('|')
        return name, int(cals)
    return "Unknown Item", 0

def ask_ai_chef(query, calories_left, ingredients):
    prompt = f"""
    I have {calories_left} calories left. 
    My ingredients: {ingredients}.
    User asks: '{query}'.
    Suggest a short recipe or snack.
    """
    return get_ai_response(prompt)

# --- App Layout ---
st.set_page_config(page_title="SisFit Mobile", page_icon="🦋", layout="centered", initial_sidebar_state="collapsed")

# 1. HEADER & USER SWITCHER (Compact)
col_head_1, col_head_2 = st.columns([3, 1])
with col_head_1:
    st.title("🦋 SisFit")
with col_head_2:
    user = st.selectbox("User", ["Me", "Sister"], label_visibility="collapsed")

# Load Data
df_data = load_csv(DATA_FILE)
df_profiles = load_csv(PROFILE_FILE)
df_menu = load_csv(MENU_FILE)

# Combine Menu
full_menu = BASE_MENU.copy()
if not df_menu.empty:
    for index, row in df_menu.iterrows():
        full_menu.append(row.to_dict())

# Repair Data (Hidden)
if not df_data.empty:
    for col in ["meal_type", "notes"]:
        if col not in df_data.columns: df_data[col] = ""
    if "calories" not in df_data.columns: df_data["calories"] = 0
    if "weight" not in df_data.columns: df_data["weight"] = 0.0

# --- PROFILE CHECK ---
user_profile_data = df_profiles[df_profiles["user"] == user] if not df_profiles.empty else pd.DataFrame()

if user_profile_data.empty:
    st.info(f"👋 Hi {user}! Create your profile below.")
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
    # --- MAIN DASHBOARD ---
    user_profile = user_profile_data.iloc[0]
    
    # NZ Date Format Logic
    today_obj = datetime.now()
    today_str_nz = today_obj.strftime("%d/%m/%Y") # Display format
    today_str_iso = today_obj.strftime("%Y-%m-%d") # Logic format
    
    calories_today = 0
    user_history = df_data[df_data["user"] == user].copy() if not df_data.empty else pd.DataFrame()
    
    if not user_history.empty:
        user_history["dt"] = pd.to_datetime(user_history["date"])
        todays_logs = user_history[user_history["dt"].dt.strftime("%Y-%m-%d") == today_str_iso]
        calories_today = todays_logs["calories"].sum()
        latest_weight = user_history.iloc[-1]['weight']
    else:
        latest_weight = user_profile["start_weight"]
    
    goal = int(user_profile["calorie_target"])
    
    # --- HERO METRICS (Big & Clean) ---
    st.markdown("---")
    m1, m2, m3 = st.columns(3)
    m1.metric("Today", int(calories_today))
    rem = goal - int(calories_today)
    m2.metric("Left", rem, delta_color="normal" if rem > 0 else "inverse")
    m3.metric("Kg", f"{latest_weight}")
    
    # Progress Bar with Color Logic
    prog = min(1.0, calories_today / goal) if goal > 0 else 0
    st.progress(prog)
    if rem < 0:
        st.caption(f"🚨 You are {abs(rem)} calories over!")

    # --- NAVIGATION TABS ---
    t_log, t_diary, t_shop, t_tools = st.tabs(["➕ Log", "📅 Diary", "🛒 List", "⚙️ Tools"])

    # --- TAB 1: LOG (Mobile Optimized) ---
    with t_log:
        st.write("### ⚡ Quick Add")
        
        # Grid Layout for Buttons
        g1, g2 = st.columns(2)
        for i, item in enumerate(full_menu):
            with (g1 if i % 2 == 0 else g2):
                if st.button(f"{item['name']}\n({item['cals']})", key=f"q_{i}", use_container_width=True):
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
        st.write("### 📸 Scan & Search")
        
        # Camera is separated to prevent reload loops
        cam_img = st.camera_input("Take Photo")
        
        ai_res_name, ai_res_cals = "", 0
        if cam_img:
            with st.spinner("🤖 Analyzing..."):
                img = Image.open(cam_img)
                ai_res_name, ai_res_cals = analyze_image(img)
            
            if "Error" in ai_res_name:
                st.error("AI Connection Failed. Try typing manually below.")
            else:
                st.success(f"Found: {ai_res_name}")

        # Unified Form
        with st.form("entry_form"):
            f_name = st.text_input("Food Name", value=ai_res_name)
            f_cals = st.number_input("Calories", value=int(ai_res_cals))
            f_type = st.selectbox("Meal", ["Breakfast", "Lunch", "Dinner", "Snack"])
            f_save = st.checkbox("Save to 'Quick Add' list?")
            
            if st.form_submit_button("✅ Save Entry", use_container_width=True):
                new_entry = {
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "user": user, "weight": latest_weight, 
                    "calories": f_cals, "notes": f_name, "meal_type": f_type
                }
                updated_data = pd.concat([df_data, pd.DataFrame([new_entry])], ignore_index=True)
                save_csv(updated_data, DATA_FILE, "Manual Entry")
                
                if f_save:
                    new_menu = {"name": f_name, "cals": f_cals, "type": f_type, "desc": f_name}
                    updated_menu = pd.concat([df_menu, pd.DataFrame([new_menu])], ignore_index=True)
                    save_csv(updated_menu, MENU_FILE, "Menu Update")
                
                st.toast("Saved!")
                time_lib.sleep(0.5)
                st.rerun()

    # --- TAB 2: DIARY (NZ DATES) ---
    with t_diary:
        st.write("### 📅 History")
        if not user_history.empty:
            # Create NZ Date Column for display
            user_history["nz_date"] = user_history["dt"].dt.strftime("%d/%m/%Y")
            days = sorted(user_history["nz_date"].unique(), reverse=True)
            
            for d in days:
                d_data = user_history[user_history["nz_date"] == d]
                total = d_data["calories"].sum()
                
                with st.expander(f"{d}  —  {int(total)} cals", expanded=(d==today_str_nz)):
                    for m in ["Breakfast", "Lunch", "Dinner", "Snack"]:
                        m_rows = d_data[d_data["meal_type"] == m]
                        if not m_rows.empty:
                            st.caption(f"**{m}**")
                            for _, r in m_rows.iterrows():
                                c_a, c_b = st.columns([3, 1])
                                c_a.write(r["notes"])
                                c_b.write(f"**{int(r['calories'])}**")
                            st.divider()

    # --- TAB 3: SHOPPING ---
    with t_shop:
        st.write("### 🛒 Shopping List")
        for cat, items in SHOPPING_LIST.items():
            with st.expander(cat):
                for i in items:
                    st.checkbox(i, key=i)

    # --- TAB 4: TOOLS (Chef + Edit) ---
    with t_tools:
        st.write("### 👨‍🍳 AI Chef")
        chef_input = st.text_input("Ask about ingredients:")
        if st.button("Ask Chef", use_container_width=True):
            all_ing = ", ".join([x for l in SHOPPING_LIST.values() for x in l])
            left = goal - int(calories_today)
            with st.spinner("Thinking..."):
                res = ask_ai_chef(chef_input, left, all_ing)
            st.info(res)

        st.divider()
        st.write("### ✏️ Edit History")
        if not user_history.empty:
            # Show simplified editor
            ed_df = st.data_editor(
                user_history[["date", "weight", "calories", "notes", "meal_type"]].sort_values("date", ascending=False),
                num_rows="dynamic",
                use_container_width=True
            )
            if st.button("💾 Save Corrections", use_container_width=True):
                others = df_data[df_data["user"] != user]
                ed_df["user"] = user
                final = pd.concat([others, ed_df], ignore_index=True)
                save_csv(final, DATA_FILE, "Edited")
                st.toast("Corrections Saved!")
                time_lib.sleep(0.5)
                st.rerun()
