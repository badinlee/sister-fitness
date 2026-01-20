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
MENU_FILE = "my_menu.csv" # New file for your custom saved meals

# --- YOUR DOCUMENTS (Hardcoded Data) ---
SHOPPING_LIST = {
    "Produce": ["Spinach/Salad Mix", "Frozen Mixed Berries (Large)", "Avocados (3-4)", "Fruit (10 pieces)", "Frozen Veg (4 bags)", "Courgettes", "Garlic & Ginger"],
    "Butchery": ["Chicken Breast (3kg)", "Eggs (1 Dozen)", "Anchor Protein+ Yogurt (2kg)", "Cheese (500g Edam/Tasty)"],
    "Pantry": ["Vogel's Bread", "Bagel Thins (Rebel)", "Rice Cups (6-8) or 1kg Bag", "Salsa (F. Whitlock's)", "Oil Spray", "Mayo/Soy/Honey/Sriracha", "Spices (Paprika, Garlic, Cajun)"]
}

# The Base Menu
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
def analyze_image(image_data):
    try:
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
st.set_page_config(page_title="SisFit Diary", page_icon="📔", layout="centered")
st.title("📔 Sister Fitness Diary")

user = st.sidebar.selectbox("User", ["Me", "Sister"])

# Load Data
df_data = load_csv(DATA_FILE)
df_profiles = load_csv(PROFILE_FILE)
df_menu = load_csv(MENU_FILE) # Custom Menu

# Combine Base Menu with User Custom Menu
full_menu = BASE_MENU.copy()
if not df_menu.empty:
    for index, row in df_menu.iterrows():
        full_menu.append(row.to_dict())

# --- DATA REPAIR ---
if not df_data.empty:
    for col in ["meal_type", "notes"]:
        if col not in df_data.columns: df_data[col] = ""
    if "calories" not in df_data.columns: df_data["calories"] = 0
    if "weight" not in df_data.columns: df_data["weight"] = 0.0

if not df_profiles.empty:
    user_profile = df_profiles[df_profiles["user"] == user].iloc[0]
    
    # --- DASHBOARD METRICS ---
    today_str = datetime.now().strftime("%Y-%m-%d")
    calories_today = 0
    user_history = df_data[df_data["user"] == user].copy() if not df_data.empty else pd.DataFrame()
    
    if not user_history.empty:
        user_history["dt"] = pd.to_datetime(user_history["date"])
        todays_logs = user_history[user_history["dt"].dt.strftime("%Y-%m-%d") == today_str]
        calories_today = todays_logs["calories"].sum()
        latest_weight = user_history.iloc[-1]['weight']
    else:
        latest_weight = user_profile["start_weight"]
    
    goal = int(user_profile["calorie_target"])
    col1, col2, col3 = st.columns(3)
    col1.metric("Today's Cals", int(calories_today))
    col2.metric("Remaining", goal - int(calories_today))
    col3.metric("Weight", f"{latest_weight}kg")

    # --- TABS ---
    tab_log, tab_diary, tab_shop, tab_chef, tab_stats = st.tabs(["➕ Add Food", "📅 Daily Diary", "🛒 List", "👨‍🍳 Chef", "📊 Stats"])

    # --- TAB 1: UNIFIED LOGGING (The "All-in-One" Input) ---
    with tab_log:
        st.subheader("Log your meal")
        
        # 1. VISUAL SELECTOR (Tabs for method)
        log_method = st.radio("How to add?", ["Quick Menu", "Scan/Photo", "Manual Entry"], horizontal=True)
        
        if log_method == "Quick Menu":
            st.caption("One-tap add from your plan:")
            cols = st.columns(2)
            for i, item in enumerate(full_menu):
                with cols[i % 2]:
                    if st.button(f"{item['name']} ({item['cals']})", key=f"btn_{i}"):
                        new_entry = {
                            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "user": user, "weight": latest_weight, 
                            "calories": item['cals'], "notes": item['desc'], 
                            "meal_type": item['type']
                        }
                        updated_data = pd.concat([df_data, pd.DataFrame([new_entry])], ignore_index=True)
                        save_csv(updated_data, DATA_FILE, f"Quick Add: {item['name']}")
                        st.success("Added!")
                        st.rerun()

        elif log_method == "Scan/Photo":
            st.caption("Take a photo of food or barcode")
            enable_cam = st.checkbox("Open Camera")
            if enable_cam:
                img_file = st.camera_input("Snap")
                if img_file:
                    with st.spinner("Analyzing..."):
                        img = Image.open(img_file)
                        ai_name, ai_cals = analyze_image(img)
                    
                    if "Error" in ai_name:
                        st.error(ai_name)
                    else:
                        st.success(f"Found: {ai_name} ({ai_cals})")
                        with st.form("scan_save"):
                            s_name = st.text_input("Name", value=ai_name)
                            s_cals = st.number_input("Calories", value=ai_cals)
                            s_type = st.selectbox("Meal", ["Breakfast", "Lunch", "Dinner", "Snack"])
                            save_quick = st.checkbox("💾 Save to 'Quick Menu' for next time?")
                            
                            if st.form_submit_button("Add Entry"):
                                # 1. Save to Diary
                                new_entry = {
                                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                    "user": user, "weight": latest_weight, 
                                    "calories": s_cals, "notes": s_name, "meal_type": s_type
                                }
                                updated_data = pd.concat([df_data, pd.DataFrame([new_entry])], ignore_index=True)
                                save_csv(updated_data, DATA_FILE, "Scan Add")
                                
                                # 2. Save to Custom Menu if checked
                                if save_quick:
                                    new_menu_item = {"name": s_name, "cals": s_cals, "type": s_type, "desc": s_name}
                                    updated_menu = pd.concat([df_menu, pd.DataFrame([new_menu_item])], ignore_index=True)
                                    save_csv(updated_menu, MENU_FILE, "New Menu Item")
                                
                                st.rerun()

        elif log_method == "Manual Entry":
            with st.form("manual_save"):
                m_name = st.text_input("Food Name (e.g. 'Oats')")
                m_cals = st.number_input("Calories", min_value=0)
                m_type = st.selectbox("Meal", ["Breakfast", "Lunch", "Dinner", "Snack"])
                save_quick = st.checkbox("💾 Save to 'Quick Menu' for next time?")
                
                if st.form_submit_button("Add Entry"):
                    new_entry = {
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "user": user, "weight": latest_weight, 
                        "calories": m_cals, "notes": m_name, "meal_type": m_type
                    }
                    updated_data = pd.concat([df_data, pd.DataFrame([new_entry])], ignore_index=True)
                    save_csv(updated_data, DATA_FILE, "Manual Add")
                    
                    if save_quick:
                        new_menu_item = {"name": m_name, "cals": m_cals, "type": m_type, "desc": m_name}
                        updated_menu = pd.concat([df_menu, pd.DataFrame([new_menu_item])], ignore_index=True)
                        save_csv(updated_menu, MENU_FILE, "New Menu Item")
                    
                    st.rerun()

    # --- TAB 2: DIARY VIEW (The "Oats + Syrup" Request) ---
    with tab_diary:
        st.subheader("📅 Your Food Diary")
        
        if not user_history.empty:
            # Group by Date
            user_history["day_str"] = user_history["dt"].dt.strftime("%Y-%m-%d")
            unique_days = sorted(user_history["day_str"].unique(), reverse=True)
            
            for day in unique_days:
                day_data = user_history[user_history["day_str"] == day]
                day_total = day_data["calories"].sum()
                
                # Create an Expander for the Day
                with st.expander(f"{day} (Total: {int(day_total)} cals)", expanded=(day==today_str)):
                    
                    # Group by Meal Type
                    meal_types = ["Breakfast", "Lunch", "Dinner", "Snack"]
                    for m_type in meal_types:
                        meal_data = day_data[day_data["meal_type"] == m_type]
                        if not meal_data.empty:
                            m_total = meal_data["calories"].sum()
                            st.markdown(f"**{m_type}** ({int(m_total)} cals)")
                            
                            # List items
                            for _, row in meal_data.iterrows():
                                col_a, col_b = st.columns([4, 1])
                                col_a.write(f"- {row['notes']}")
                                col_b.write(f"{int(row['calories'])}")
                            st.divider()
        else:
            st.info("No entries yet.")

    # --- TAB 3: SHOPPING LIST ---
    with tab_shop:
        st.subheader("🛒 Shopping List")
        for category, items in SHOPPING_LIST.items():
            st.write(f"**{category}**")
            for item in items:
                st.checkbox(item, key=item)

    # --- TAB 4: CHEF (With Error Info) ---
    with tab_chef:
        st.subheader("👨‍🍳 AI Chef")
        q = st.text_input("Ask for a recipe:")
        if st.button("Ask"):
            ingredients = ", ".join([i for cat in SHOPPING_LIST.values() for i in cat])
            left = goal - int(calories_today)
            with st.spinner("Chef is thinking..."):
                ans = ask_ai_chef(q, left, ingredients)
            
            if "Error" in ans:
                st.error("Chef is having trouble connecting. Details:")
                st.code(ans)
            else:
                st.success(ans)

    # --- TAB 5: STATS/EDIT ---
    with tab_stats:
        st.subheader("✏️ Edit History")
        if not user_history.empty:
             editable_cols = ["date", "weight", "calories", "notes", "meal_type"]
             display_df = user_history[editable_cols].sort_values("date", ascending=False)
             edited_user_df = st.data_editor(display_df, num_rows="dynamic", use_container_width=True, key="editor")
            
             if st.button("💾 Save Changes"):
                other_users_data = df_data[df_data["user"] != user]
                edited_user_df["user"] = user
                final_df = pd.concat([other_users_data, edited_user_df], ignore_index=True)
                save_csv(final_df, DATA_FILE, "Edited History")
                st.rerun()
