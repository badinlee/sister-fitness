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

def identify_food_density(query, image=None):
    prompt = (
        f"Identify the food '{query}' (or from image). "
        "Find the approximate Calories per 100g (or 100ml) for this specific brand/item. "
        "Return ONLY a string in this format: 'Food Name|CaloriesPer100g'. "
        "Example: 'Watties Baked Beans|90'. "
        "If unsure, guess based on standard nutritional data."
    )
    res = get_ai_response(prompt, image).strip()
    if '|' in res:
        parts = res.split('|')
        cals_100 = ''.join(filter(str.isdigit, parts[1]))
        return parts[0], int(cals_100) if cals_100 else 0
    return "Unknown", 0

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
    today_str_nz = today_obj.strftime("%d/%m/%Y")
    today_str_iso = today_obj.strftime("%Y-%m-%d")
    
    calories_today = 0
    latest_weight = user_profile["start_weight"]
    
    user_history = df_data[df_data["user"] == user].copy() if not df_data.empty else pd.DataFrame()
    if not user_history.empty:
        user_history["dt"] = pd.to_datetime(user_history["date"])
        user_history["nz_date_str"] = user_history["dt"].dt.strftime("%d/%m/%Y") 
        user_history["nice_date"] = user_history["dt"].dt.strftime("%a %d %b")
        
        todays_logs = user_history[user_history["dt"].dt.strftime("%Y-%m-%d") == today_str_iso]
        calories_today = todays_logs["calories"].sum()
        latest_weight = user_history.iloc[-1]['weight']
    
    goal = int(user_profile["calorie_target"])
    
    # Hero Stats
    st.markdown("---")
    m1, m2, m3 = st.columns(3)
    m1.metric("Today", int(calories_today))
    m2.metric("Left", goal - int(calories_today))
    m3.metric("Kg", f"{latest_weight}")
    
    # Tabs
    t_add, t_diary, t_edit, t_shop = st.tabs(["➕ Log Food", "📅 Diary", "✏️ Edit/Fix", "🛒 List"])

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
        st.write("### 🔎 Search & Weigh")
        
        col_scan, col_search = st.columns([1, 2])
        cam_input = col_scan.camera_input("Scan")
        search_query = col_search.text_input("Or Type Food (e.g. Watties Beans)")
        
        if 'calc_name' not in st.session_state: st.session_state['calc_name'] = ""
        if 'calc_density' not in st.session_state: st.session_state['calc_density'] = 0
        
        # Trigger Search
        if cam_input or (search_query and st.button("Search")):
            with st.spinner("Finding Nutrition Info..."):
                img = Image.open(cam_input) if cam_input else None
                txt = search_query if search_query else "Food image"
                f_name, f_density = identify_food_density(txt, img)
                st.session_state['calc_name'] = f_name
                st.session_state['calc_density'] = f_density

        # Calculator
        if st.session_state['calc_density'] > 0:
            st.success(f"**Found:** {st.session_state['calc_name']} (~{st.session_state['calc_density']} cals/100g)")
            
            with st.form("gram_calc"):
                grams = st.number_input("How many grams?", 0, 2000, 100, step=10)
                meal_type = st.selectbox("Meal", ["Breakfast", "Lunch", "Dinner", "Snack"])
                total_cals = int((grams / 100) * st.session_state['calc_density'])
                st.write(f"### = {total_cals} Calories")
                
                save_quick = st.checkbox("Save to Quick Menu?")

                if st.form_submit_button("✅ Track It", use_container_width=True):
                    final_note = f"{st.session_state['calc_name']} ({grams}g)"
                    new_entry = {
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "user": user, "weight": latest_weight, 
                        "calories": total_cals, "notes": final_note, "meal_type": meal_type
                    }
                    updated_data = pd.concat([df_data, pd.DataFrame([new_entry])], ignore_index=True)
                    save_csv(updated_data, DATA_FILE, "Tracked")
                    
                    if save_quick:
                        new_menu = {"name": final_note, "cals": total_cals, "type": meal_type, "desc": final_note}
                        updated_menu = pd.concat([df_menu, pd.DataFrame([new_menu])], ignore_index=True)
                        save_csv(updated_menu, MENU_FILE, "Menu Update")

                    st.session_state['calc_density'] = 0
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
                    c_d1, c_d2 = st.columns([2,1])
                    c_d1.subheader(day_str)
                    
                    st.markdown(f"**Used:** {int(day_total)} | **Left:** {int(day_rem)}")
                    st.divider()
                    
                    for m in ["Breakfast", "Lunch", "Dinner", "Snack"]:
                        m_data = day_data[day_data["meal_type"] == m]
                        if not m_data.empty:
                            st.caption(f"**{m}**")
                            for _, r in m_data.iterrows():
                                c_a, c_b = st.columns([4, 1])
                                c_a.write(f"{r['notes']}")
                                c_b.write(f"**{int(r['calories'])}**")

    # --- TAB 3: EASY EDIT (New!) ---
    with t_edit:
        st.subheader("✏️ Fix Mistakes")
        st.info("Tap any cell below to change the number. Then click Save.")
        
        if not user_history.empty:
            # Full screen editor
            edited_df = st.data_editor(
                user_history[["date", "calories", "notes", "meal_type"]].sort_values("date", ascending=False),
                num_rows="dynamic",
                use_container_width=True,
                height=500 # Taller editor
            )
            
            if st.button("💾 Save All Corrections", use_container_width=True):
                # Re-merge logic
                others = df_data[df_data["user"] != user]
                edited_df["user"] = user
                edited_df["weight"] = latest_weight
                
                final_df = pd.concat([others, edited_df], ignore_index=True)
                save_csv(final_df, DATA_FILE, "Bulk Edit")
                st.toast("✅ Corrections Saved!")
                time_lib.sleep(1)
                st.rerun()
        else:
            st.write("No history to edit yet.")

    # --- TAB 4: SHOPPING ---
    with t_shop:
        st.write("### 🛒 Shopping List")
        for cat, items in SHOPPING_LIST.items():
            with st.expander(cat):
                for i in items:
                    st.checkbox(i, key=i)
