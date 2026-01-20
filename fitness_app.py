import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from github import Github
import io
import plotly.express as px  # New charting tool

# --- Configuration ---
REPO_NAME = "badinlee/sister-fitness" # YOUR REPO NAME HERE
FILE_PATH = "data.csv"

# Update with REAL data! (Height is in meters, e.g., 1.65)
GOALS = {
    "Me": {"target_weight": 65.0, "daily_calories": 1800, "height": 1.75},
    "Sister": {"target_weight": 60.0, "daily_calories": 1600, "height": 1.65}
}

# --- GitHub Functions (Same as before) ---
def get_github_repo():
    g = Github(st.secrets["GITHUB_TOKEN"])
    return g.get_repo(REPO_NAME)

def load_data():
    try:
        repo = get_github_repo()
        contents = repo.get_contents(FILE_PATH)
        return pd.read_csv(io.StringIO(contents.decoded_content.decode()))
    except:
        return pd.DataFrame(columns=["date", "user", "weight", "calories"])

def save_data(new_entry):
    repo = get_github_repo()
    df = load_data()
    new_df = pd.concat([df, pd.DataFrame([new_entry])], ignore_index=True)
    csv_content = new_df.to_csv(index=False)
    try:
        contents = repo.get_contents(FILE_PATH)
        repo.update_file(contents.path, "New entry", csv_content, contents.sha)
    except:
        repo.create_file(FILE_PATH, "First entry", csv_content)

# --- Helper: Calculate Streaks ---
def get_streak(user_df):
    if user_df.empty: return 0
    # Convert dates to datetime objects
    user_df["date_obj"] = pd.to_datetime(user_df["date"]).dt.date
    dates = sorted(user_df["date_obj"].unique(), reverse=True)
    
    today = datetime.now().date()
    streak = 0
    
    # Check if we logged today
    if dates and dates[0] == today:
        streak = 1
        current_check = today - timedelta(days=1)
    else:
        current_check = today
        
    # Count backwards
    for d in dates:
        if d == current_check:
            streak += 1
            current_check -= timedelta(days=1)
    return streak

# --- App Layout ---
st.set_page_config(page_title="SisFit 2.0", page_icon="🔥")

st.title("🔥 Sister Fitness Tracker")

# Sidebar for Navigation
user = st.sidebar.selectbox("Select User", ["Me", "Sister"])
target_w = GOALS[user]["target_weight"]
height = GOALS[user]["height"]

# --- 1. Top Dashboard (Quick Stats) ---
df = load_data()
user_data = df[df["user"] == user].copy() if not df.empty else pd.DataFrame()

col1, col2, col3 = st.columns(3)

# Metric 1: Current Weight
if not user_data.empty:
    latest_weight = user_data.iloc[-1]["weight"]
    delta = latest_weight - user_data.iloc[-2]["weight"] if len(user_data) > 1 else 0
    col1.metric("Current Weight", f"{latest_weight} kg", f"{delta:.1f} kg", delta_color="inverse")
else:
    col1.metric("Current Weight", "--", "--")

# Metric 2: BMI
if not user_data.empty:
    bmi = latest_weight / (height ** 2)
    col2.metric("Current BMI", f"{bmi:.1f}")
else:
    col2.metric("BMI", "--")

# Metric 3: Streak
streak = get_streak(user_data)
col3.metric("Login Streak", f"{streak} Days", "Keep it up!")

# --- 2. Goal Progress Bar ---
if not user_data.empty:
    st.write(f"**Goal Progress ({target_w} kg)**")
    # Simple calculation for progress bar (0 to 100)
    start_weight = user_data.iloc[0]["weight"]
    total_loss_needed = start_weight - target_w
    current_loss = start_weight - latest_weight
    
    if total_loss_needed > 0:
        progress = max(0.0, min(1.0, current_loss / total_loss_needed))
        st.progress(progress)
        if progress >= 1.0:
            st.balloons() # Celebration if goal hit!

# --- 3. Input Form ---
st.divider()
st.subheader("📝 Daily Check-in")
with st.form("entry_form"):
    w = st.number_input("Today's Weight", min_value=0.0, format="%.1f")
    c = st.number_input("Calories", min_value=0, step=50)
    submit = st.form_submit_button("Save Update")
    
    if submit:
        entry = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "user": user,
            "weight": w,
            "calories": c
        }
        with st.spinner("Updating database..."):
            save_data(entry)
        st.success("Log saved!")
        st.rerun() # Refresh page instantly

# --- 4. Interactive Chart ---
st.divider()
st.subheader("📈 History")
if not df.empty:
    # Use Plotly for interactive chart
    fig = px.line(df, x="date", y="weight", color="user", markers=True, title="Weight Progress")
    st.plotly_chart(fig)
