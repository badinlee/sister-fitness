import streamlit as st
import pandas as pd
from datetime import datetime, date
from github import Github
import io
import plotly.express as px

# --- Configuration ---
REPO_NAME = "badinlee/sister-fitness"  # <--- UPDATE THIS!
DATA_FILE = "data.csv"
PROFILE_FILE = "profiles.csv"

# --- "Mini AI" Food Database (Calories per 1 gram) ---
FOOD_DB = {
    "apple": 0.52, "banana": 0.89, "orange": 0.47, "grapes": 0.69,
    "chicken breast (cooked)": 1.65, "ground beef": 2.50, "salmon": 2.08,
    "egg (1 large)": 78, "bread (1 slice)": 80, "rice (cooked)": 1.30,
    "pasta (cooked)": 1.31, "potato (boiled)": 0.87, "oats": 3.89,
    "milk (1 cup)": 103, "cheese (cheddar)": 4.02, "yogurt": 0.59,
    "chocolate": 5.46, "pizza (slice)": 266, "burger": 295
}

# --- GitHub Connection ---
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

# --- App Logic ---
st.set_page_config(page_title="SisFit AI", page_icon="🥗", layout="centered")
st.title("🥗 Sister Fitness: Meal Tracker")

# 1. User Selection
user = st.sidebar.selectbox("Who is eating?", ["Me", "Sister"])

# 2. Load Data
df_data = load_csv(DATA_FILE)
df_profiles = load_csv(PROFILE_FILE)

# Get Profile
if df_profiles.empty:
    st.error("Please run the previous code once to create your profile!")
    st.stop()

user_profile = df_profiles[df_profiles["user"] == user].iloc[0]

# --- DASHBOARD LOGIC ---
today_str = datetime.now().strftime("%Y-%m-%d")

# Filter data for THIS USER
user_history = df_data[df_data["user"] == user].copy() if not df_data.empty else pd.DataFrame()

# Calculate TODAY'S Totals
calories_today = 0
foods_today = []

if not user_history.empty:
    # Add a date column string for matching
    user_history["date_str"] = pd.to_datetime(user_history["date"]).dt.strftime("%Y-%m-%d")
    
    # Get just today's rows
    todays_logs = user_history[user_history["date_str"] == today_str]
    
    # Sum up the calories
    calories_today = todays_logs["calories"].sum()
    foods_today = todays_logs

# --- TOP METRICS ---
col1, col2 = st.columns(2)
goal = int(user_profile["calorie_target"])
left = goal - calories_today

col1.metric("Calories Eaten", f"{int(calories_today)}", delta=f"{int(calories_today)} today", delta_color="off")
col2.metric("Calories Left", f"{int(left)}", delta=f"Goal: {goal}", delta_color="normal")

# Progress Bar
if goal > 0:
    prog = min(1.0, calories_today / goal)
    st.progress(prog)
    if left < 0:
        st.warning(f"⚠️ You are {abs(left)} calories over your limit!")

# --- SMART FOOD LOGGER ---
st.divider()
st.subheader("🍽️ Log a Meal")

tab1, tab2 = st.tabs(["🍎 Smart Search", "✍️ Manual Add"])

# TAB 1: SMART SEARCH
with tab1:
    st.write("Search for a food to auto-calculate calories:")
    
    # Search box
    search_term = st.selectbox("Select Food", [""] + list(FOOD_DB.keys()))
    
    calc_cals = 0
    quantity = 0
    note = ""
    
    if search_term:
        factor = FOOD_DB[search_term]
        
        # Logic for "per unit" vs "per gram" items
        if factor > 10: # Likely a "per unit" item like Egg or Slice of Bread
            quantity = st.number_input(f"How many {search_term}s?", 1, 10, 1)
            calc_cals = quantity * factor
            st.info(f"🧮 {quantity} x {factor} cal = **{int(calc_cals)} calories**")
            note = f"{quantity} {search_term}"
        else: # Likely a "per gram" item like Chicken or Apple
            quantity = st.number_input("How many grams?", 0, 1000, 100)
            calc_cals = quantity * factor
            st.info(f"🧮 {quantity}g x {factor} cal/g = **{int(calc_cals)} calories**")
            note = f"{quantity}g {search_term}"
            
        if st.button("Add Smart Food"):
            new_entry = {
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "user": user,
                "weight": user_history.iloc[-1]["weight"] if not user_history.empty else user_profile["start_weight"], # Carry over last weight
                "calories": int(calc_cals),
                "notes": note
            }
            # Save
            updated_data = pd.concat([df_data, pd.DataFrame([new_entry])], ignore_index=True)
            with st.spinner("Adding to log..."):
                save_csv(updated_data, DATA_FILE, f"Added {note}")
            st.success("Added!")
            st.rerun()

# TAB 2: MANUAL ADD
with tab2:
    with st.form("manual_add"):
        m_desc = st.text_input("Food Description (e.g. 'Sandwich')")
        m_cals = st.number_input("Calories", 0, 2000, 0)
        
        if st.form_submit_button("Add Manual Entry"):
            new_entry = {
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "user": user,
                "weight": user_history.iloc[-1]["weight"] if not user_history.empty else user_profile["start_weight"],
                "calories": m_cals,
                "notes": m_desc
            }
            updated_data = pd.concat([df_data, pd.DataFrame([new_entry])], ignore_index=True)
            save_csv(updated_data, DATA_FILE, "Manual Log")
            st.rerun()

# --- TODAY'S LOG ---
st.divider()
st.subheader(f"📅 Today's Menu ({today_str})")

if not foods_today.empty:
    # Show a clean table of just food and calories
    display_table = foods_today[["notes", "calories", "date"]].copy()
    # Format the time nicely
    display_table["time"] = pd.to_datetime(display_table["date"]).dt.strftime("%H:%M")
    st.dataframe(display_table[["time", "notes", "calories"]], hide_index=True, use_container_width=True)
else:
    st.caption("Nothing logged yet today.")

# --- WEIGHT LOGGING (Moved to bottom) ---
with st.expander("⚖️ Log Weight Check-in"):
    with st.form("weight_in"):
        w = st.number_input("Current Weight", value=float(user_profile["start_weight"]))
        if st.form_submit_button("Update Weight"):
             new_entry = {
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "user": user,
                "weight": w,
                "calories": 0, # Weight entry has 0 calories
                "notes": "Weight Check-in"
            }
             updated_data = pd.concat([df_data, pd.DataFrame([new_entry])], ignore_index=True)
             save_csv(updated_data, DATA_FILE, "Weight Update")
             st.rerun()
