import streamlit as st
import pandas as pd
from datetime import datetime

# --- Configuration ---
# Simple goals for demonstration
GOALS = {
    "Me": {"target_weight": 65.0, "daily_calories": 1800},
    "Sister": {"target_weight": 60.0, "daily_calories": 1600}
}

# --- 1. The Setup ---
st.set_page_config(page_title="SisFit AI Tracker", page_icon="💪")

st.title("💪 Sister Fitness & AI Tracker")

# Select who is using the app
user = st.selectbox("Who is checking in?", ["Me", "Sister"])

# --- 2. Input Section ---
st.header(f"Good Morning, {user}! ☀️")

with st.form("daily_entry"):
    # Weight Input
    current_weight = st.number_input("Current Weight (kg)", min_value=0.0, format="%.1f")
    
    # Food Input
    calories_eaten = st.number_input("Calories Eaten Today", min_value=0)
    
    # Submit button
    submitted = st.form_submit_button("Save Entry")

    if submitted:
        # In a real app, we would save this to a database/Google Sheet
        # For now, we save it to the session so we can see it work immediately
        entry = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "user": user,
            "weight": current_weight,
            "calories": calories_eaten
        }
        if "data" not in st.session_state:
            st.session_state["data"] = []
        st.session_state["data"].append(entry)
        st.success("Saved! Great job checking in.")

# --- 3. Dashboard & History ---
st.divider()
st.header("📊 Progress Report")

if "data" in st.session_state and st.session_state["data"]:
    # Convert list to a nice table
    df = pd.DataFrame(st.session_state["data"])
    
    # Filter for the current user
    user_data = df[df["user"] == user]
    
    if not user_data.empty:
        st.dataframe(user_data)

        # Simple Chart
        st.line_chart(user_data, x="date", y="weight")
    else:
        st.info("No data for you yet. Add an entry above!")
else:
    st.write("No entries yet.")

# --- 4. The AI Coach Logic ---
st.divider()
st.header("🤖 AI Coach Feedback")

if submitted:
    target = GOALS[user]["target_weight"]
    cal_limit = GOALS[user]["daily_calories"]
    
    # Simple Logic (This is where we could plug in ChatGPT later)
    advice = ""
    
    # Weight check
    if current_weight > target:
        diff = current_weight - target
        advice += f"You are {diff:.1f}kg away from your goal. "
    elif current_weight <= target:
        advice += "You hit your weight goal! Amazing! 🎉 "
        
    # Calorie check
    if calories_eaten > cal_limit:
        advice += f"\n\n⚠️ You went over your calorie limit by {calories_eaten - cal_limit}. Try a lighter dinner tonight."
    elif calories_eaten > 0:
        advice += f"\n\n✅ You are within your calorie budget. Keep it up!"
        

    st.info(advice)
