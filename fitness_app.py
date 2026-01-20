import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
from github import Github
import io
import plotly.express as px

# --- Configuration ---
REPO_NAME = "badinlee/sister-fitness"  # <--- UPDATE THIS
DATA_FILE = "data.csv"
PROFILE_FILE = "profiles.csv"

# --- "Mini AI" Food Database ---
FOOD_DB = {
    "apple": 0.52, "banana": 0.89, "orange": 0.47, "grapes": 0.69,
    "chicken breast": 1.65, "ground beef": 2.50, "salmon": 2.08,
    "egg (1 large)": 78, "bread (1 slice)": 80, "rice (cooked)": 1.30,
    "pasta (cooked)": 1.31, "potato (boiled)": 0.87, "oats": 3.89,
    "milk (1 cup)": 103, "cheese": 4.02, "yogurt": 0.59,
    "chocolate": 5.46, "pizza": 266, "burger": 295, "avocado": 1.60
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

# --- AI Logic: Metabolic Calculator ---
def calculate_bmr(weight_kg, height_m, age):
    # Mifflin-St Jeor Equation (Women)
    # BMR = (10 x weight) + (6.25 x height_cm) - (5 x age) - 161
    return (10 * weight_kg) + (6.25 * (height_m * 100)) - (5 * age) - 161

# --- App Logic ---
st.set_page_config(page_title="SisFit Coach", page_icon="🧬", layout="centered")
st.title("🧬 Sister Fitness AI Coach")

user = st.sidebar.selectbox("Who is checking in?", ["Me", "Sister"])
df_data = load_csv(DATA_FILE)
df_profiles = load_csv(PROFILE_FILE)

# --- 1. PROFILE CHECK ---
# We check if profile exists AND if it has 'age' (since we just added that requirement)
need_setup = False
if df_profiles.empty:
    need_setup = True
elif user not in df_profiles["user"].values:
    need_setup = True
elif "age" not in df_profiles.columns:
    st.warning("⚠️ We need to add your Age to calculate accurate metabolism.")
    need_setup = True

if need_setup:
    st.info(f"Welcome {user}! Let's calibrate your AI Coach.")
    with st.form("setup_profile"):
        height = st.number_input("Height (m)", 1.0, 2.5, 1.65)
        age = st.number_input("Age", 18, 100, 30)
        start_w = st.number_input("Current Weight (kg)", 40.0, 200.0, 70.0)
        goal_w = st.number_input("Goal Weight (kg)", 40.0, 200.0, 60.0)
        goal_date = st.date_input("Target Date")
        
        # Auto-calculate initial calories
        initial_bmr = calculate_bmr(start_w, height, age)
        suggested_cals = int(initial_bmr * 1.2 - 500) # Deficit
        cal_goal = st.number_input("Daily Calorie Goal (Auto-suggested)", 1000, 4000, suggested_cals)
        
        if st.form_submit_button("Save Profile"):
            new_profile = {
                "user": user, "height": height, "age": age,
                "start_weight": start_w, "goal_weight": goal_w,
                "goal_date": goal_date, "calorie_target": cal_goal
            }
            # Handle creating new or updating existing df
            if "age" not in df_profiles.columns and not df_profiles.empty:
                # If adding age column to old data
                df_profiles["age"] = 30 # Default for others
            
            # Remove old entry for user if exists
            df_profiles = df_profiles[df_profiles["user"] != user]
            updated_profiles = pd.concat([df_profiles, pd.DataFrame([new_profile])], ignore_index=True)
            
            with st.spinner("Calibrating..."):
                save_csv(updated_profiles, PROFILE_FILE, f"Profile update for {user}")
            st.rerun()

# --- 2. MAIN DASHBOARD ---
else:
    user_profile = df_profiles[df_profiles["user"] == user].iloc[0]
    user_history = df_data[df_data["user"] == user].copy() if not df_data.empty else pd.DataFrame()
    
    # Get latest weight
    current_w = user_history.iloc[-1]["weight"] if not user_history.empty else user_profile["start_weight"]
    
    # --- 🤖 THE AI COACH SECTION ---
    with st.expander("🤖 AI Coach Analysis", expanded=True):
        # 1. Calculate stats
        bmr = calculate_bmr(current_w, user_profile["height"], user_profile["age"])
        tdee = bmr * 1.2 # Sedentary multiplier
        current_target = user_profile["calorie_target"]
        
        # 2. Check if adjustment needed
        # To lose 0.5kg/week, need 500 cal deficit
        ideal_target = int(tdee - 500)
        
        # Logic: If the gap between current target and ideal is > 100 cals
        diff = current_target - ideal_target
        
        col_a, col_b = st.columns([3, 1])
        with col_a:
            st.caption(f"Based on your current weight of **{current_w}kg**:")
            if diff > 100:
                st.warning(f"⚠️ **Adjustment Needed:** Your body now burns fewer calories than when you started. To keep losing weight efficiently, you should lower your intake.")
                st.write(f"Current Goal: **{current_target}** → Recommended: **{ideal_target}**")
                
                # THE MAGIC BUTTON
                if st.button("✅ Update My Calorie Goal"):
                    df_profiles.loc[df_profiles["user"] == user, "calorie_target"] = ideal_target
                    save_csv(df_profiles, PROFILE_FILE, "AI Goal Adjustment")
                    st.success("Goal updated!")
                    st.rerun()
                    
            elif diff < -100:
                st.info("💡 You can actually eat a bit more and still hit your goals!")
                st.write(f"Current Goal: **{current_target}** → Recommended: **{ideal_target}**")
            else:
                st.success("✅ **You are perfectly on track.** Your calorie goal matches your metabolic needs.")

    # --- 3. TODAY'S TRACKER ---
    today_str = datetime.now().strftime("%Y-%m-%d")
    calories_today = 0
    if not user_history.empty:
        user_history["date_str"] = pd.to_datetime(user_history["date"]).dt.strftime("%Y-%m-%d")
        todays_logs = user_history[user_history["date_str"] == today_str]
        calories_today = todays_logs["calories"].sum()

    # Metrics
    left = int(user_profile["calorie_target"]) - int(calories_today)
    col1, col2, col3 = st.columns(3)
    col1.metric("Today's Cals", int(calories_today))
    col2.metric("Remaining", left, delta_color="normal" if left > 0 else "inverse")
    col3.metric("Current Weight", f"{current_w}kg")

    # --- 4. LOGGING FORMS ---
    st.divider()
    tab1, tab2 = st.tabs(["🍎 Log Food", "⚖️ Log Weight"])
    
    with tab1:
        c1, c2 = st.columns([2,1])
        with c1:
            search = st.selectbox("Quick Add Food", [""] + list(FOOD_DB.keys()))
        with c2:
            qty = st.number_input("Grams/Qty", 1, 500, 100)
            
        if st.button("Add Food"):
            cal_val = 0
            note = ""
            if search:
                factor = FOOD_DB[search]
                if factor > 10: # Unit item
                    cal_val = qty * factor
                    note = f"{qty} {search}"
                else: # Gram item
                    cal_val = qty * factor
                    note = f"{qty}g {search}"
            else:
                # If no food selected, assume manual entry (needs extra input logic, simplified here)
                st.error("Please select a food or update code for manual entry")
            
            if cal_val > 0:
                new_entry = {
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "user": user,
                    "weight": current_w, # Keep weight same
                    "calories": int(cal_val),
                    "notes": note
                }
                updated_data = pd.concat([df_data, pd.DataFrame([new_entry])], ignore_index=True)
                save_csv(updated_data, DATA_FILE, f"Ate {note}")
                st.rerun()
                
    with tab2:
        new_w = st.number_input("New Weight (kg)", 0.0, 200.0, float(current_w))
        if st.button("Save Weight"):
             new_entry = {
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "user": user,
                "weight": new_w,
                "calories": 0,
                "notes": "Weight Check-in"
            }
             updated_data = pd.concat([df_data, pd.DataFrame([new_entry])], ignore_index=True)
             save_csv(updated_data, DATA_FILE, "Weight Update")
             st.rerun()

    # --- 5. PROGRESS CHART ---
    st.divider()
    if not user_history.empty:
        fig = px.line(user_history, x="date", y="weight", title="Weight Loss Journey")
        fig.add_hline(y=user_profile["goal_weight"], line_dash="dash", line_color="green", annotation_text="GOAL")
        st.plotly_chart(fig)
