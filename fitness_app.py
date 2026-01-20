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
        return pd.read_csv(io.StringIO(contents.decoded_content.decode()))
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

# --- AI Vision Logic (Updated for Barcodes) ---
def analyze_image(image_data):
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = (
            "Analyze this image. It might be food, a barcode, or a nutrition label. "
            "1. If it's a barcode or nutrition label: Extract the product name and calories per serving. "
            "2. If it's a meal photo: Estimate the calories. "
            "Return ONLY a string in this exact format: 'Food Name|Calories'. "
            "Example: 'Oat Bar|180'. If unknown, return 'Error|0'."
        )
        response = model.generate_content([prompt, image_data])
        text = response.text.strip()
        if '|' in text:
            name, cals = text.split('|')
            return name, int(cals)
        return "Unknown Item", 0
    except:
        return "Error analyzing", 0

# --- App Layout ---
st.set_page_config(page_title="SisFit Editor", page_icon="✏️", layout="centered")
st.title("✏️ Sister Fitness: Smart Editor")

user = st.sidebar.selectbox("User", ["Me", "Sister"])
df_data = load_csv(DATA_FILE)
df_profiles = load_csv(PROFILE_FILE)

if not df_profiles.empty:
    user_profile = df_profiles[df_profiles["user"] == user].iloc[0]
    
    # --- DASHBOARD METRICS ---
    today_str = datetime.now().strftime("%Y-%m-%d")
    calories_today = 0
    
    # Filter data for User
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
    col3.metric("Current Weight", f"{latest_weight}kg")

    # --- TABS ---
    st.divider()
    tab1, tab2, tab3, tab4 = st.tabs(["📸 Scan/Barcode", "⭐ Favorites", "📝 Manual", "✏️ Edit History"])

    # --- SHARED HELPERS ---
    meal_options = ["Breakfast", "Lunch", "Dinner", "Snack"]
    current_hour = datetime.now().time()

    # --- TAB 1: AI SCANNER (UPDATED) ---
    with tab1:
        st.subheader("Scan Food, Barcode, or Label")
        enable_cam = st.checkbox("Open Camera")
        img_file_buffer = None
        if enable_cam:
            img_file_buffer = st.camera_input("Take a picture")

        if img_file_buffer is not None:
            with st.spinner("Reading Barcode/Food..."):
                image = Image.open(img_file_buffer)
                food_name, food_cals = analyze_image(image)
            
            st.success(f"Detected: **{food_name}** ({food_cals} cals)")
            
            with st.form("ai_confirm"):
                a_name = st.text_input("Name", value=food_name)
                a_cals = st.number_input("Calories", value=food_cals)
                a_type = st.selectbox("Meal Type", meal_options, index=1)
                
                if st.form_submit_button("✅ Add Log"):
                    log_dt = datetime.combine(date.today(), current_hour)
                    new_entry = {
                        "date": log_dt.strftime("%Y-%m-%d %H:%M"),
                        "user": user,
                        "weight": latest_weight,
                        "calories": a_cals,
                        "notes": a_name,
                        "meal_type": a_type
                    }
                    updated_data = pd.concat([df_data, pd.DataFrame([new_entry])], ignore_index=True)
                    save_csv(updated_data, DATA_FILE, f"AI Log: {a_name}")
                    st.rerun()

    # --- TAB 2: FAVORITES ---
    with tab2:
        if not user_history.empty:
            past_meals = user_history[user_history["calories"] > 0]["notes"].unique()
            selected_meal = st.selectbox("Select a recent meal:", ["-- Choose --"] + list(past_meals))
            
            if selected_meal != "-- Choose --":
                last_entry = user_history[user_history["notes"] == selected_meal].iloc[-1]
                with st.form("fav_add"):
                    f_name = st.text_input("Meal Name", value=selected_meal)
                    f_cals = st.number_input("Calories", value=int(last_entry["calories"]))
                    f_type = st.selectbox("Meal Type", meal_options)
                    f_time = st.time_input("Time Eaten", value=current_hour)
                    
                    if st.form_submit_button("Add to Log"):
                        log_dt = datetime.combine(date.today(), f_time)
                        new_entry = {
                            "date": log_dt.strftime("%Y-%m-%d %H:%M"),
                            "user": user,
                            "weight": latest_weight,
                            "calories": f_cals,
                            "notes": f_name,
                            "meal_type": f_type
                        }
                        updated_data = pd.concat([df_data, pd.DataFrame([new_entry])], ignore_index=True)
                        save_csv(updated_data, DATA_FILE, f"Added favorite: {f_name}")
                        st.rerun()

    # --- TAB 3: MANUAL ---
    with tab3:
        with st.form("manual_log"):
            m_name = st.text_input("Food Description")
            m_cals = st.number_input("Calories", min_value=0, step=10)
            m_type = st.selectbox("Meal Type", meal_options)
            m_time = st.time_input("Time Eaten", value=current_hour)
            
            if st.form_submit_button("Add Entry"):
                log_dt = datetime.combine(date.today(), m_time)
                new_entry = {
                    "date": log_dt.strftime("%Y-%m-%d %H:%M"),
                    "user": user,
                    "weight": latest_weight,
                    "calories": m_cals,
                    "notes": m_name,
                    "meal_type": m_type
                }
                updated_data = pd.concat([df_data, pd.DataFrame([new_entry])], ignore_index=True)
                save_csv(updated_data, DATA_FILE, "Manual Log")
                st.rerun()

    # --- TAB 4: EDIT HISTORY (THE FIX!) ---
    with tab4:
        st.subheader("✏️ Edit or Delete Entries")
        st.info("Double-click any cell to edit it. Select rows and press 'Delete' on your keyboard to remove them.")
        
        if not user_history.empty:
            # 1. Show the Data Editor (Excel style)
            # We filter columns to make it cleaner
            editable_cols = ["date", "weight", "calories", "notes", "meal_type"]
            
            # We use the FULL dataframe for editing, but filter display for the user
            # This allows us to map changes back to the original database
            
            edited_user_df = st.data_editor(
                user_history[editable_cols].sort_values("date", ascending=False),
                num_rows="dynamic", # Allows adding/deleting rows
                use_container_width=True,
                key="editor"
            )
            
            if st.button("💾 Save Changes to Cloud"):
                # 2. Reconstruct the full database
                # We take the EDITED user history and combine it with the OTHER user's data
                other_users_data = df_data[df_data["user"] != user]
                
                # Add the 'user' column back to the edited data (since we hid it)
                edited_user_df["user"] = user
                
                # Combine
                final_df = pd.concat([other_users_data, edited_user_df], ignore_index=True)
                
                with st.spinner("Saving corrections..."):
                    save_csv(final_df, DATA_FILE, "Edited History")
                st.success("Changes Saved!")
                st.rerun()
