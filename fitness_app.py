import streamlit as st
import pandas as pd
from datetime import datetime
from github import Github
import io

# --- Configuration ---
REPO_NAME = "badinlee/sister-fitness"  # Make sure this matches your username/repo exactly
FILE_PATH = "data.csv"
GOALS = {
    "Me": {"target_weight": 65.0, "daily_calories": 1800},
    "Sister": {"target_weight": 60.0, "daily_calories": 1600}
}

# --- GitHub Connection Functions ---
def get_github_repo():
    # This grabs the token we saved in Streamlit Secrets
    g = Github(st.secrets["GITHUB_TOKEN"])
    return g.get_repo(REPO_NAME)

def load_data():
    try:
        repo = get_github_repo()
        # Try to get the file
        contents = repo.get_contents(FILE_PATH)
        return pd.read_csv(io.StringIO(contents.decoded_content.decode()))
    except:
        # If file doesn't exist yet, return empty database
        return pd.DataFrame(columns=["date", "user", "weight", "calories"])

def save_data(new_entry):
    repo = get_github_repo()
    df = load_data()
    
    # Add new entry
    new_df = pd.concat([df, pd.DataFrame([new_entry])], ignore_index=True)
    
    # Convert to CSV string
    csv_content = new_df.to_csv(index=False)
    
    try:
        # If file exists, update it
        contents = repo.get_contents(FILE_PATH)
        repo.update_file(contents.path, "New entry", csv_content, contents.sha)
    except:
        # If file doesn't exist, create it
        repo.create_file(FILE_PATH, "First entry", csv_content)

# --- App Layout ---
st.set_page_config(page_title="SisFit AI Tracker", page_icon="💪")
st.title("💪 Sister Fitness & AI Tracker")

# Select User
user = st.selectbox("Who is checking in?", ["Me", "Sister"])

# --- Input Form ---
st.header(f"Good Morning, {user}! ☀️")
with st.form("daily_entry"):
    current_weight = st.number_input("Current Weight (kg)", min_value=0.0, format="%.1f")
    calories_eaten = st.number_input("Calories Eaten Today", min_value=0)
    submitted = st.form_submit_button("Save Entry")

    if submitted:
        entry = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "user": user,
            "weight": current_weight,
            "calories": calories_eaten
        }
        with st.spinner("Saving to the cloud..."):
            save_data(entry)
        st.success("Saved! Your sister can see this now.")

# --- Dashboard ---
st.divider()
st.header("📊 Progress Report")

# Load fresh data
df = load_data()

if not df.empty:
    # Show stats
    user_data = df[df["user"] == user]
    if not user_data.empty:
        st.line_chart(user_data, x="date", y="weight")
        st.dataframe(user_data.tail(5)) # Show last 5 entries
    else:
        st.info("No data for you yet.")
else:
    st.write("Start by adding your first entry above!")
