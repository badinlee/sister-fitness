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

# --- ROBUST AI LOGIC (Classic Model Fallback) ---
def get_ai_response(prompt, image=None):
    """Attempts to use Gemini Pro (Classic) which is most stable."""
    try:
        if image:
            # Use the classic vision model
            model = genai.GenerativeModel('gemini-pro-vision')
            response = model.generate_content([prompt, image])
        else:
            # Use the classic text model
            model = genai.GenerativeModel('gemini-pro')
            response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error: {str(e)}"

def calculate_calories_from_grams(food_name, grams):
    prompt = f"How many calories are in {grams} grams of {food_name}? Return ONLY the integer number. Do not write text."
    res = get_ai_response(prompt)
    # Clean up response to get just the number
    clean_res = ''.join(filter(str.isdigit, res))
    if clean_res:
        return int(clean_res)
    return 0

def analyze_image(image_data):
    prompt = (
        "Analyze this image. It might be food, a barcode, or a nutrition label. "
        "Return ONLY a string: 'Food Name|Calories'. Example: 'Oat Bar|180'. "
        "If unknown, return 'Unknown|0'."
    )
    text = get_ai_response(prompt, image_data).strip()
    if '|' in text:
        parts = text.split('|')
        return parts[0], int(parts[1])
    return "Unknown Item", 0

def ask_ai_chef(query, calories_left, ingredients):
    prompt = f"""
    I have {calories_left} calories left today.
    My available ingredients: {ingredients}.
    User query: '{query}'.
    Suggest a short, healthy recipe or snack option.
    """
    return get_ai_response(prompt)

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

# Combine Menu
full_menu = BASE_MENU.copy()
if not df_menu.empty:
    for index, row in df_menu.iterrows():
        full_menu.append(row.to_dict())

# Repair Data
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
    # --- DASHBOARD ---
    user_profile = user_profile_data.iloc[0]
    
    # Dates
    today_obj = datetime.now()
    today_str_nz = today_obj.strftime("%d/%m/%Y")
    today_str_iso = today_obj.strftime("%Y-%m-%d")
    
    # Filter Today
    user_history = df_data[df_data["user"] == user].copy() if not df_data.empty else pd.DataFrame()
    calories_today = 0
    
    if not user_history.empty:
        user_history["dt"] = pd.to_datetime(user_history["date"])
        # Add NZ Date string for grouping
        user_history["nz_date_str"] = user_history["dt"].dt.strftime("%d/%m/%Y") 
        # Add nice text date string (e.g. "Tue 20 Jan")
        user_history["nice_date"] = user_history["dt"].dt.strftime("%a %d %b")
        
        todays_logs = user_history[user_history["dt"].dt.strftime("%Y-%m-%d") == today_str_iso]
        calories_today = todays_logs["calories"].sum()
        latest_weight = user_history.iloc[-1]['weight']
    else:
        latest_weight = user_profile["start_weight"]
    
    goal = int(user_profile["calorie_target"])
    
    # Top Stats
    st.markdown("---")
    m1, m2, m3 = st.columns(3)
    m1.metric("Today", int(calories_today))
    rem = goal - int(calories_today)
    m2.metric("Remaining", rem, delta_color="normal" if rem > 0 else "inverse")
    m3.metric("Weight", f"{latest_weight}kg")
    
    # Tabs
    t_add, t_diary, t_shop, t_chef = st.tabs(["➕ Log Food", "📅 Diary", "🛒 List", "👨‍🍳 Chef"])

    # --- TAB 1: LOGGING ---
    with t_add:
        # 1. GRAM CALCULATOR (New Feature!)
        with st.expander("⚖️ Gram Calculator (Watties etc)", expanded=True):
            col_g1, col_g2, col_g3 = st.columns([2,1,1])
            calc_food = col_g1.text_input("Food (e.g. Baked Beans)", placeholder="Watties Baked Beans")
            calc_grams = col_g2.number_input("Grams", 0, 1000, 100)
            
            if col_g3.button("Calculate"):
                with st.spinner("Calculating..."):
                    calc_res = calculate_calories_from_grams(calc_food, calc_grams)
                if calc_res > 0:
                    st.success(f"**{calc_res} Calories** in {calc_grams}g of {calc_food}")
                    # Save to session state to auto-fill form below
                    st.session_state['auto_name'] = f"{calc_grams}g {calc_food}"
                    st.session_state['auto_cals'] = calc_res
                else:
                    st.error("Could not calculate. Check AI connection.")

        st.divider()

        # 2. QUICK BUTTONS
        st.caption("⚡ Quick Add")
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
        st.caption("📸 Scanner")
        
        # Camera
        cam_input = st.camera_input("Take Photo")
        if cam_input:
            with st.spinner("Analyzing..."):
                img = Image.open(cam_input)
                ai_name, ai_cals = analyze_image(img)
            if "Error" in ai_name:
                st.error("Scanner Error.")
            else:
                st.success(f"Found: {ai_name} ({ai_cals})")
                st.session_state['auto_name'] = ai_name
                st.session_state['auto_cals'] = ai_cals

        st.divider()
        st.caption("✍️ Confirm Entry")
        
        # Unified Form - checks session state for auto-filled values
        default_name = st.session_state.get('auto_name', "")
        default_cals = st.session_state.get('auto_cals', 0)

        with st.form("entry_form"):
            f_name = st.text_input("Food Name", value=default_name)
            f_cals = st.number_input("Calories", value=int(default_cals))
            f_type = st.selectbox("Meal", ["Breakfast", "Lunch", "Dinner", "Snack"])
            f_save = st.checkbox("Save to 'Quick Add'?")
            
            if st.form_submit_button("✅ Save Log", use_container_width=True):
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
                
                # Clear session state
                if 'auto_name' in st.session_state: del st.session_state['auto_name']
                if 'auto_cals' in st.session_state: del st.session_state['auto_cals']
                
                st.toast("Saved!")
                time_lib.sleep(0.5)
                st.rerun()

    # --- TAB 2: DIARY ---
    with t_diary:
        if not user_history.empty:
            days_df = user_history.sort_values("dt", ascending=False).drop_duplicates(subset=["nice_date"])
            unique_days = days_df["nice_date"].tolist()
            
            for day_str in unique_days:
                day_data = user_history[user_history["nice_date"] == day_str]
                day_total = day_data["calories"].sum()
                day_rem = goal - day_total
                
                with st.container(border=True):
                    st.subheader(day_str)
                    # Summary Line
                    c_sum1, c_sum2 = st.columns(2)
                    c_sum1.metric("Used", f"{int(day_total)}")
                    c_sum2.metric("Remaining", f"{int(day_rem)}", delta_color="normal" if day_rem > 0 else "inverse")
                    
                    st.divider()
                    
                    # Meals
                    for m in ["Breakfast", "Lunch", "Dinner", "Snack"]:
                        m_data = day_data[day_data["meal_type"] == m]
                        if not m_data.empty:
                            st.write(f"**{m}**")
                            for _, r in m_data.iterrows():
                                c_a, c_b = st.columns([3, 1])
                                c_a.caption(f"{r['notes']}")
                                c_b.caption(f"{int(r['calories'])}")
                            st.markdown("")

        else:
            st.info("No logs yet.")
            
        with st.expander("⚙️ Edit / Delete Entries"):
            if not user_history.empty:
                ed_df = st.data_editor(user_history[["date", "calories", "notes", "meal_type"]], use_container_width=True)
                if st.button("💾 Save Corrections"):
                    others = df_data[df_data["user"] != user]
                    ed_df["user"] = user
                    ed_df["weight"] = latest_weight 
                    final = pd.concat([others, ed_df], ignore_index=True)
                    save_csv(final, DATA_FILE, "Edited")
                    st.toast("Updated!")
                    st.rerun()

    # --- TAB 3: SHOPPING ---
    with t_shop:
        st.write("### 🛒 Shopping List")
        for cat, items in SHOPPING_LIST.items():
            with st.expander(cat):
                for i in items:
                    st.checkbox(i, key=i)

    # --- TAB 4: CHEF ---
    with t_chef:
        st.write("### 👨‍🍳 AI Chef")
        c_q = st.text_input("Ask about ingredients:")
        if st.button("Ask Chef", use_container_width=True):
            all_ing = ", ".join([x for l in SHOPPING_LIST.values() for x in l])
            left = goal - int(calories_today)
            with st.spinner("Thinking..."):
                ans = ask_ai_chef(c_q, left, all_ing)
            st.info(ans)
