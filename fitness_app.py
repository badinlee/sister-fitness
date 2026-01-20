import streamlit as st
import pandas as pd
from datetime import datetime, date, time
from github import Github
import io
import plotly.express as px
import google.generativeai as genai
from PIL import Image

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

# --- AI Logic (STABLE MODEL) ---
def analyze_image(image_data):
    try:
        # 'gemini-1.5-flash' is the stable standard model
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = (
            "Analyze this image. It might be food, a barcode, or a nutrition label. "
            "Return ONLY a string: 'Food Name|Calories'. Example: 'Oat Bar|180'. "
            "If unknown, return 'Unknown|0'."
        )
        response = model.generate_content([prompt, image_data])
        text = response.text.strip()
        if '|' in text:
            name, cals = text.split('|')
            return name, int(cals)
        return "Unknown Item", 0
    except Exception as e:
        # Fallback error message
        return f"Error: {str(e)}", 0

def ask_ai_chef(query, calories_left, ingredients):
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"""
        I have {calories_left} calories left. 
        My ingredients: {ingredients}.
        User asks: '{query}'.
        Suggest a recipe or snack.
        """
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Chef Error: {str(e)}"

# --- App Layout ---
st.set_page_config(page_title="SisFit Mobile", page_icon="🦋", layout="centered", initial_sidebar_state="collapsed")

# 1. TOP NAVIGATION (Mobile Friendly)
# Instead of Sidebar, we use columns at the top for easy switching
c1, c2 = st.columns([3, 1])
with c1:
    st.title("🦋 SisFit")
with c2:
    # Small User Switcher at top right
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
    
    # NZ Date Format (DD/MM/YYYY)
    today_str_nz = datetime.now().strftime("%d/%m/%Y")
    today_str_iso = datetime.now().strftime("%Y-%m-%d") # for filtering
    
    calories_today = 0
    user_history = df_data[df_data["user"] == user].copy() if not df_data.empty else pd.DataFrame()
    
    if not user_history.empty:
        user_history["dt"] = pd.to_datetime(user_history["date"])
        # Filter strictly by ISO date string
        todays_logs = user_history[user_history["dt"].dt.strftime("%Y-%m-%d") == today_str_iso]
        calories_today = todays_logs["calories"].sum()
        latest_weight = user_history.iloc[-1]['weight']
    else:
        latest_weight = user_profile["start_weight"]
    
    goal = int(user_profile["calorie_target"])
    
    # --- METRICS BAR ---
    # Using a container to make it pop
    with st.container():
        col1, col2, col3 = st.columns(3)
        col1.metric("Today", int(calories_today))
        remaining = goal - int(calories_today)
        col2.metric("Left", remaining, delta_color="normal" if remaining > 0 else "inverse")
        col3.metric("Kg", f"{latest_weight}")
        st.progress(min(1.0, calories_today / goal) if goal > 0 else 0)

    # --- MAIN TABS ---
    # We use emojis as tab names to save space on mobile
    tab_add, tab_diary, tab_list, tab_more = st.tabs(["➕ Log", "📅 Diary", "🛒 List", "⚙️ More"])

    # --- TAB 1: LOGGING (Mobile Optimized) ---
    with tab_add:
        # Toggle between Quick and Manual/Scan
        mode = st.radio("Mode", ["⚡ Quick Plan", "📸 Scan & Search"], horizontal=True, label_visibility="collapsed")
        
        if mode == "⚡ Quick Plan":
            st.caption("Tap to add instantly:")
            # GRID LAYOUT for buttons
            grid_cols = st.columns(2)
            for i, item in enumerate(full_menu):
                with grid_cols[i % 2]:
                    # Short label for mobile
                    if st.button(f"{item['name']}\n({item['cals']})", key=f"btn_{i}", use_container_width=True):
                        new_entry = {
                            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "user": user, "weight": latest_weight, 
                            "calories": item['cals'], "notes": item['desc'], "meal_type": item['type']
                        }
                        updated_data = pd.concat([df_data, pd.DataFrame([new_entry])], ignore_index=True)
                        save_csv(updated_data, DATA_FILE, "Quick Add")
                        st.toast(f"✅ Added {item['name']}!") # Toast notification
                        # No rerun needed, toast is enough feedback usually, but rerun updates stats
                        time.sleep(1) 
                        st.rerun()

        else: # Scan & Search Mode
            st.info("Take a photo OR type a name.")
            
            # Unified Input Form
            with st.form("unified_input"):
                c_cam, c_txt = st.columns([1, 2])
                
                # Camera inside the form logic is tricky in Streamlit, 
                # so we put the input OUTSIDE and just use the result here.
                pass 
            
            # Camera Input (Must be outside form to trigger reload)
            img_file = st.camera_input("📸 Camera")
            
            # Helper to process image if it exists
            ai_name, ai_cals = "", 0
            if img_file:
                with st.spinner("Analyzing..."):
                    img = Image.open(img_file)
                    ai_name, ai_cals = analyze_image(img)
                if "Error" in ai_name:
                    st.error(ai_name)
                else:
                    st.success(f"Detected: {ai_name} ({ai_cals} cals)")
            
            # The Form
            with st.form("manual_scan_form"):
                st.write("Confirm Details:")
                # If AI found something, use it as default value
                f_name = st.text_input("Food Name", value=ai_name)
                f_cals = st.number_input("Calories", value=int(ai_cals))
                f_type = st.selectbox("Meal", ["Breakfast", "Lunch", "Dinner", "Snack"])
                f_save = st.checkbox("Save to Quick Plan?")
                
                if st.form_submit_button("Add Entry", use_container_width=True):
                    new_entry = {
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "user": user, "weight": latest_weight, 
                        "calories": f_cals, "notes": f_name, "meal_type": f_type
                    }
                    updated_data = pd.concat([df_data, pd.DataFrame([new_entry])], ignore_index=True)
                    save_csv(updated_data, DATA_FILE, "Entry Added")
                    
                    if f_save:
                        new_menu = {"name": f_name, "cals": f_cals, "type": f_type, "desc": f_name}
                        updated_menu = pd.concat([df_menu, pd.DataFrame([new_menu])], ignore_index=True)
                        save_csv(updated_menu, MENU_FILE, "Menu Updated")
                    
                    st.toast("✅ Entry Saved!")
                    st.rerun()

    # --- TAB 2: DIARY (NZ FORMAT) ---
    with tab_diary:
        st.subheader("📅 History")
        if not user_history.empty:
            # Create NZ Date Strings (DD/MM/YYYY)
            user_history["nz_date"] = user_history["dt"].dt.strftime("%d/%m/%Y")
            unique_days = sorted(user_history["nz_date"].unique(), reverse=True)
            
            for day in unique_days:
                day_data = user_history[user_history["nz_date"] == day]
                total = day_data["calories"].sum()
                
                # Expandable Day
                with st.expander(f"{day}  —  {int(total)} cals", expanded=(day == today_str_nz)):
                    for m in ["Breakfast", "Lunch", "Dinner", "Snack"]:
                        m_data = day_data[day_data["meal_type"] == m]
                        if not m_data.empty:
                            st.caption(f"**{m}**")
                            for _, row in m_data.iterrows():
                                # Grid for alignment
                                c_a, c_b = st.columns([3, 1])
                                c_a.write(f"{row['notes']}")
                                c_b.write(f"**{int(row['calories'])}**")
                            st.divider()

    # --- TAB 3: SHOPPING ---
    with tab_list:
        st.subheader("🛒 Shopping")
        for cat, items in SHOPPING_LIST.items():
            with st.expander(cat, expanded=False):
                for i in items:
                    st.checkbox(i, key=i)

    # --- TAB 4: MORE (Chef & Edit) ---
    with tab_more:
        st.write("### 👨‍🍳 AI Chef")
        chef_q = st.text_input("Ask about ingredients:")
        if st.button("Ask Chef", use_container_width=True):
             ings = ", ".join([i for cat in SHOPPING_LIST.values() for i in cat])
             left = goal - int(calories_today)
             with st.spinner("Thinking..."):
                 ans = ask_ai_chef(chef_q, left, ings)
             st.info(ans)
             
        st.divider()
        st.write("### ✏️ Edit Data")
        if not user_history.empty:
            edit_df = st.data_editor(user_history[["date", "weight", "calories", "notes", "meal_type"]].sort_values("date", ascending=False), num_rows="dynamic", use_container_width=True)
            if st.button("💾 Save Edits", use_container_width=True):
                 others = df_data[df_data["user"] != user]
                 edit_df["user"] = user
                 final = pd.concat([others, edit_df], ignore_index=True)
                 save_csv(final, DATA_FILE, "Edited")
                 st.toast("✅ Corrections Saved")
                 st.rerun()
