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

# --- AI Vision Logic ---
def get_calories_from_photo(image_data):
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = (
            "Analyze this food image. Identify the food item and estimate the total calories. "
            "Return ONLY a string in this exact format: 'Food Name|Calories'. "
            "Example: 'Slice of Pizza|280'. If not food, return 'Error|0'."
        )
        response = model.generate_content([prompt, image_data])
        text = response.text.strip()
        if '|' in text:
            name, cals = text.split('|')
            return name, int(cals)
        return "Unknown Food", 0
    except:
        return "Error analyzing", 0

# --- App Layout ---
st.set_page_config(page_title="SisFit Memory", page_icon="🧠", layout="centered")
st.title("🧠 Sister Fitness: Smart Log")

user = st.sidebar.selectbox("User", ["Me", "Sister"])
df_data = load_csv(DATA_FILE)
df_profiles = load_csv(PROFILE_FILE)

if not df_profiles.empty:
    user_profile = df_profiles[df_profiles["user"] == user].iloc[0]
    
    # --- DASHBOARD METRICS ---
    today_str = datetime.now().strftime("%Y-%m-%d")
    calories_today = 0
    
    # Filter data for User & Today
    user_history = df_data[df_data["user"] == user].copy() if not df_data.empty else pd.DataFrame()
    
    if not user_history.empty:
        # Ensure 'date' is datetime compatible
        user_history["dt"] = pd.to_datetime(user_history["date"])
        todays_logs = user_history[user_history["dt"].dt.strftime("%Y-%m-%d") == today_str]
        calories_today = todays_logs["calories"].sum()
    
    goal = int(user_profile["calorie_target"])
    col1, col2, col3 = st.columns(3)
    col1.metric("Today's Cals", int(calories_today))
    col2.metric("Remaining", goal - int(calories_today))
    col3.metric("Current Weight", f"{user_history.iloc[-1]['weight']}kg" if not user_history.empty else "--")

    # --- TABS ---
    st.divider()
    tab1, tab2, tab3, tab4 = st.tabs(["⭐ Favorites", "📸 AI Camera", "📝 Manual Log", "📊 History"])

    # --- SHARED INPUT FIELDS HELPERS ---
    # We use these to standardize the input form across tabs
    meal_options = ["Breakfast", "Lunch", "Dinner", "Snack"]
    current_hour = datetime.now().time()
    
    # --- TAB 1: FAVORITES (MEMORY) ---
    with tab1:
        st.subheader("Quick Add from History")
        if not user_history.empty:
            # Get unique food names from history (excluding weights)
            # We filter out entries with 0 calories (usually weight check-ins)
            past_meals = user_history[user_history["calories"] > 0]["notes"].unique()
            
            # Dropdown to select a past meal
            selected_meal = st.selectbox("Select a recent meal:", ["-- Choose --"] + list(past_meals))
            
            if selected_meal != "-- Choose --":
                # Find the last time you ate this to get the calories
                last_entry = user_history[user_history["notes"] == selected_meal].iloc[-1]
                saved_cals = int(last_entry["calories"])
                
                st.info(f"Memory: You last logged **{selected_meal}** as **{saved_cals} calories**.")
                
                with st.form("fav_add"):
                    # Auto-filled fields
                    f_name = st.text_input("Meal Name", value=selected_meal)
                    f_cals = st.number_input("Calories", value=saved_cals)
                    f_type = st.selectbox("Meal Type", meal_options)
                    f_time = st.time_input("Time Eaten", value=current_hour)
                    
                    if st.form_submit_button("Add to Log"):
                        # Combine Today's Date + Selected Time
                        log_dt = datetime.combine(date.today(), f_time)
                        
                        new_entry = {
                            "date": log_dt.strftime("%Y-%m-%d %H:%M"),
                            "user": user,
                            "weight": user_history.iloc[-1]["weight"],
                            "calories": f_cals,
                            "notes": f_name,
                            "meal_type": f_type
                        }
                        updated_data = pd.concat([df_data, pd.DataFrame([new_entry])], ignore_index=True)
                        save_csv(updated_data, DATA_FILE, f"Added favorite: {f_name}")
                        st.success("Logged!")
                        st.rerun()
        else:
            st.info("No history yet! Log some meals manually or with AI first.")

    # --- TAB 2: AI CAMERA ---
    with tab2:
        st.subheader("Snap & Log")
        enable_cam = st.checkbox("Open Camera")
        img_file_buffer = None
        if enable_cam:
            img_file_buffer = st.camera_input("Take a picture")

        if img_file_buffer is not None:
            with st.spinner("Analyzing..."):
                image = Image.open(img_file_buffer)
                food_name, food_cals = get_calories_from_photo(image)
            
            st.success(f"Detected: {food_name} (~{food_cals} cals)")
            
            with st.form("ai_confirm"):
                a_name = st.text_input("Name", value=food_name)
                a_cals = st.number_input("Calories", value=food_cals)
                a_type = st.selectbox("Meal Type", meal_options, index=1) # Default to Lunch
                a_time = st.time_input("Time Eaten", value=current_hour)
                
                if st.form_submit_button("✅ Add Log"):
                    log_dt = datetime.combine(date.today(), a_time)
                    new_entry = {
                        "date": log_dt.strftime("%Y-%m-%d %H:%M"),
                        "user": user,
                        "weight": user_history.iloc[-1]["weight"] if not user_history.empty else 70,
                        "calories": a_cals,
                        "notes": a_name,
                        "meal_type": a_type
                    }
                    updated_data = pd.concat([df_data, pd.DataFrame([new_entry])], ignore_index=True)
                    save_csv(updated_data, DATA_FILE, f"AI Log: {a_name}")
                    st.rerun()

    # --- TAB 3: MANUAL LOG ---
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
                    "weight": user_history.iloc[-1]["weight"] if not user_history.empty else 70,
                    "calories": m_cals,
                    "notes": m_name,
                    "meal_type": m_type
                }
                updated_data = pd.concat([df_data, pd.DataFrame([new_entry])], ignore_index=True)
                save_csv(updated_data, DATA_FILE, "Manual Log")
                st.rerun()

    # --- TAB 4: HISTORY ---
    with tab4:
        if not user_history.empty:
            st.write("Recent Activity")
            # Show table with new columns
            display_cols = ["date", "meal_type", "notes", "calories"]
            # Check if meal_type exists (for old data)
            if "meal_type" not in user_history.columns:
                user_history["meal_type"] = "Log"
            
            st.dataframe(user_history[display_cols].sort_values("date", ascending=False).head(10), hide_index=True)
            
            # Simple Chart
            fig = px.bar(user_history.tail(14), x="date", y="calories", color="meal_type", title="Calories by Meal")
            st.plotly_chart(fig)
