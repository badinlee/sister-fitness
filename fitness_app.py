import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from github import Github
import io
import plotly.express as px

# --- Configuration ---
REPO_NAME = "badinlee/sister-fitness"  # <--- UPDATE THIS
DATA_FILE = "data.csv"
PROFILE_FILE = "profiles.csv"

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
st.set_page_config(page_title="SisFit Pro", page_icon="🦋", layout="centered")

st.title("🦋 Sister Fitness Pro")

# 1. User Selection
user = st.sidebar.selectbox("Who is this?", ["Me", "Sister"])

# 2. Load Data
df_data = load_csv(DATA_FILE)
df_profiles = load_csv(PROFILE_FILE)

# Helper: Get current user profile
user_profile = pd.DataFrame()
if not df_profiles.empty:
    user_profile = df_profiles[df_profiles["user"] == user]

# --- MODE 1: ONBOARDING (If no profile exists) ---
if user_profile.empty:
    st.info(f"Welcome, {user}! Let's set up your goals.")
    
    with st.form("setup_profile"):
        st.subheader("🎯 Set Your Goals")
        height = st.number_input("Height (meters, e.g. 1.65)", 1.0, 2.5, 1.65)
        start_w = st.number_input("Starting Weight (kg)", 0.0, 200.0, 70.0)
        goal_w = st.number_input("Goal Weight (kg)", 0.0, 200.0, 60.0)
        goal_date = st.date_input("Target Date")
        cal_goal = st.number_input("Daily Calorie Goal", 1000, 4000, 1800)
        
        if st.form_submit_button("Create Profile"):
            new_profile = {
                "user": user,
                "height": height,
                "start_weight": start_w,
                "goal_weight": goal_w,
                "goal_date": goal_date,
                "calorie_target": cal_goal
            }
            # Append to profiles dataframe
            updated_profiles = pd.concat([df_profiles, pd.DataFrame([new_profile])], ignore_index=True)
            with st.spinner("Creating profile..."):
                save_csv(updated_profiles, PROFILE_FILE, f"Created profile for {user}")
            st.success("Profile Saved! Refreshing...")
            st.rerun()

# --- MODE 2: DASHBOARD (If profile exists) ---
else:
    # Extract profile vars
    profile = user_profile.iloc[0]
    
    # --- Sidebar: Edit Goals ---
    with st.sidebar.expander("⚙️ Edit My Goals"):
        with st.form("edit_goals"):
            new_goal_w = st.number_input("Goal Weight", value=float(profile["goal_weight"]))
            new_cal_goal = st.number_input("Calorie Goal", value=int(profile["calorie_target"]))
            new_date = st.date_input("Target Date", value=pd.to_datetime(profile["goal_date"]))
            
            if st.form_submit_button("Update Goals"):
                # Update specific row
                df_profiles.loc[df_profiles["user"] == user, "goal_weight"] = new_goal_w
                df_profiles.loc[df_profiles["user"] == user, "calorie_target"] = new_cal_goal
                df_profiles.loc[df_profiles["user"] == user, "goal_date"] = new_date
                save_csv(df_profiles, PROFILE_FILE, "Updated goals")
                st.rerun()

    # --- Daily Logic Check ---
    today_str = datetime.now().strftime("%Y-%m-%d")
    user_logs = df_data[df_data["user"] == user].copy() if not df_data.empty else pd.DataFrame()
    
    # Check if logged today
    logged_today = False
    if not user_logs.empty:
        user_logs["date_only"] = pd.to_datetime(user_logs["date"]).dt.strftime("%Y-%m-%d")
        if today_str in user_logs["date_only"].values:
            logged_today = True

    # --- NOTIFICATIONS ---
    if not logged_today:
        st.error("⚠️ You haven't logged yet today! Don't break the streak!")
    else:
        st.success("✅ Logged for today. Great job!")

    # --- PROGRESS SECTION ---
    col1, col2, col3 = st.columns(3)
    
    # Weight Stats
    current_w = user_logs.iloc[-1]["weight"] if not user_logs.empty else profile["start_weight"]
    to_go = current_w - profile["goal_weight"]
    
    col1.metric("Current Weight", f"{current_w} kg", delta=f"{to_go:.1f} kg to go", delta_color="inverse")
    
    # Timeline Stats
    days_left = (pd.to_datetime(profile["goal_date"]).date() - date.today()).days
    col2.metric("Days Remaining", f"{days_left} days")
    
    # Calorie Stats (Last Entry)
    last_cals = user_logs.iloc[-1]["calories"] if logged_today else 0
    cal_diff = int(profile["calorie_target"]) - last_cals
    col3.metric("Calories Left", f"{cal_diff}", delta_color="normal")

    # --- INPUT FORM ---
    st.divider()
    st.subheader("📝 Add Today's Entry")
    with st.form("daily_entry"):
        w_input = st.number_input("Weight (kg)", value=float(current_w))
        c_input = st.number_input("Calories Eaten", value=0)
        notes = st.text_input("Notes (e.g. 'Ate pizza', 'Went for run')")
        
        if st.form_submit_button("Save Log"):
            entry = {
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "user": user,
                "weight": w_input,
                "calories": c_input,
                "notes": notes
            }
            # Add to data
            updated_data = pd.concat([df_data, pd.DataFrame([entry])], ignore_index=True)
            save_csv(updated_data, DATA_FILE, "New Daily Log")
            st.rerun()

    # --- CHARTS ---
    st.divider()
    if not user_logs.empty:
        tab1, tab2 = st.tabs(["📉 Weight Trend", "🍎 Calorie History"])
        
        with tab1:
            fig = px.line(user_logs, x="date", y="weight", markers=True, title="Weight Journey")
            # Add a horizontal line for the goal
            fig.add_hline(y=profile["goal_weight"], line_dash="dash", line_color="green", annotation_text="Goal")
            st.plotly_chart(fig)
            
        with tab2:
            fig2 = px.bar(user_logs, x="date", y="calories", title="Daily Intake")
            fig2.add_hline(y=profile["calorie_target"], line_color="red", annotation_text="Limit")
            st.plotly_chart(fig2)
