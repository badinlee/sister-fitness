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
            "1. If it's a barcode or nutrition label: Extract the product name and calories per serving. "
            "2. If it's a meal photo: Estimate the calories. "
            "Return ONLY a string in this exact format: 'Food Name|Calories'. "
            "Example: 'Oat Bar|180'. If unknown, return 'Unknown Item|0'."
        )
        response = model.generate_content([prompt, image_data])
        text = response.text.strip()
        if '|' in text:
            name, cals = text.split('|')
            return name, int(cals)
        return "Unknown Item", 0
    except:
        return "Error analyzing", 0

def ask_ai_chef(query, calories_left):
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"I am on a diet and have {calories_left} calories left today. The user asks: '{query}'. Give a short, healthy suggestion or recipe."
        response = model.generate_content(prompt)
        return response.text
    except:
        return "AI Chef is sleeping. Try again later."

# --- App Layout ---
st.set_page_config(page_title="SisFit Ultimate", page_icon="🦋", layout="centered")
st.title("🦋 Sister Fitness Ultimate")

user = st.sidebar.selectbox("User", ["Me", "Sister"])
df_data = load_csv(DATA_FILE)
df_profiles = load_csv(PROFILE_FILE)

# --- 🛠️ DATA REPAIR SQUAD ---
if not df_data.empty:
    for col in ["meal_type", "notes"]:
        if col not in df_data.columns: df_data[col] = ""
    if "calories" not in df_data.columns: df_data["calories"] = 0
    if "weight" not in df_data.columns: df_data["weight"] = 0.0

if not df_profiles.empty:
    user_profile = df_profiles[df_profiles["user"] == user].iloc[0]
    
    # --- SIDEBAR: AI CHEF ---
    with st.sidebar.expander("👨‍🍳 AI Kitchen Helper"):
        chef_query = st.text_input("Ask for a recipe/snack:")
        if st.button("Ask Chef"):
            # Calculate remaining calories for context
            today_str = datetime.now().strftime("%Y-%m-%d")
            user_hist = df_data[df_data["user"]==user] if not df_data.empty else pd.DataFrame()
            cals_today = 0
            if not user_hist.empty:
                user_hist["dt"] = pd.to_datetime(user_hist["date"])
                cals_today = user_hist[user_hist["dt"].dt.strftime("%Y-%m-%d")==today_str]["calories"].sum()
            left = int(user_profile["calorie_target"]) - int(cals_today)
            
            answer = ask_ai_chef(chef_query, left)
            st.info(answer)

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
    col3.metric("Current Weight", f"{latest_weight}kg")

    # --- TABS ---
    st.divider()
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["🏆 Sister Showdown", "📸 Scan/Barcode", "⭐ Favorites", "📝 Manual", "✏️ Editor"])

    meal_options = ["Breakfast", "Lunch", "Dinner", "Snack"]
    current_hour = datetime.now().time()

    # --- TAB 1: SISTER SHOWDOWN (NEW!) ---
    with tab1:
        st.subheader("🔥 Sister vs Sister")
        if not df_data.empty:
            # 1. Comparison Chart
            fig = px.line(df_data, x="date", y="weight", color="user", markers=True, title="Weight Progress Comparison")
            st.plotly_chart(fig)
            
            # 2. Leaderboard Logic
            st.write("### 🏅 Leaderboard")
            users = df_data["user"].unique()
            scores = []
            
            for u in users:
                u_data = df_data[df_data["user"] == u]
                if not u_data.empty:
                    start_w = u_data.iloc[0]["weight"]
                    curr_w = u_data.iloc[-1]["weight"]
                    loss_kg = start_w - curr_w
                    loss_pct = (loss_kg / start_w) * 100
                    scores.append({"User": u, "Loss %": loss_pct, "Kg Lost": loss_kg})
            
            if scores:
                score_df = pd.DataFrame(scores).sort_values("Loss %", ascending=False)
                st.dataframe(score_df, hide_index=True)
                
                winner = score_df.iloc[0]["User"]
                st.success(f"🎉 Current Leader: **{winner}** is crushing it!")

    # --- TAB 2: AI SCANNER ---
    with tab2:
        st.subheader("Scan Barcode or Food")
        enable_cam = st.checkbox("Open Camera")
        img_file_buffer = None
        if enable_cam:
            img_file_buffer = st.camera_input("Snap Pic")

        if img_file_buffer is not None:
            with st.spinner("AI Reading..."):
                image = Image.open(img_file_buffer)
                food_name, food_cals = analyze_image(image)
            
            st.success(f"Found: **{food_name}** ({food_cals} cals)")
            with st.form("ai_confirm"):
                a_name = st.text_input("Name", value=food_name)
                a_cals = st.number_input("Calories", value=food_cals)
                a_type = st.selectbox("Type", meal_options, index=1)
                if st.form_submit_button("✅ Add"):
                    log_dt = datetime.combine(date.today(), current_hour)
                    new_entry = {
                        "date": log_dt.strftime("%Y-%m-%d %H:%M"),
                        "user": user, "weight": latest_weight, "calories": a_cals,
                        "notes": a_name, "meal_type": a_type
                    }
                    updated_data = pd.concat([df_data, pd.DataFrame([new_entry])], ignore_index=True)
                    save_csv(updated_data, DATA_FILE, f"AI Log: {a_name}")
                    st.rerun()

    # --- TAB 3: FAVORITES ---
    with tab3:
        if not user_history.empty:
            valid_history = user_history.dropna(subset=["notes"])
            if not valid_history.empty:
                past_meals = valid_history[valid_history["calories"] > 0]["notes"].unique()
                selected_meal = st.selectbox("Quick Add:", ["-- Choose --"] + list(past_meals))
                
                if selected_meal != "-- Choose --":
                    last_entry = user_history[user_history["notes"] == selected_meal].iloc[-1]
                    with st.form("fav_add"):
                        f_name = st.text_input("Name", value=selected_meal)
                        f_cals = st.number_input("Cals", value=int(last_entry["calories"]))
                        f_type = st.selectbox("Type", meal_options)
                        f_time = st.time_input("Time", value=current_hour)
                        if st.form_submit_button("Add"):
                            log_dt = datetime.combine(date.today(), f_time)
                            new_entry = {
                                "date": log_dt.strftime("%Y-%m-%d %H:%M"),
                                "user": user, "weight": latest_weight, "calories": f_cals,
                                "notes": f_name, "meal_type": f_type
                            }
                            updated_data = pd.concat([df_data, pd.DataFrame([new_entry])], ignore_index=True)
                            save_csv(updated_data, DATA_FILE, f"Fav: {f_name}")
                            st.rerun()

    # --- TAB 4: MANUAL ---
    with tab4:
        with st.form("manual_log"):
            m_name = st.text_input("Food")
            m_cals = st.number_input("Cals", min_value=0, step=10)
            m_type = st.selectbox("Type", meal_options)
            m_time = st.time_input("Time", value=current_hour)
            if st.form_submit_button("Add"):
                log_dt = datetime.combine(date.today(), m_time)
                new_entry = {
                    "date": log_dt.strftime("%Y-%m-%d %H:%M"),
                    "user": user, "weight": latest_weight, "calories": m_cals,
                    "notes": m_name, "meal_type": m_type
                }
                updated_data = pd.concat([df_data, pd.DataFrame([new_entry])], ignore_index=True)
                save_csv(updated_data, DATA_FILE, "Manual Log")
                st.rerun()

    # --- TAB 5: EDITOR ---
    with tab5:
        st.subheader("✏️ Edit History")
        st.info("Edit cells below and click Save.")
        if not user_history.empty:
            editable_cols = ["date", "weight", "calories", "notes", "meal_type"]
            display_df = user_history[editable_cols].sort_values("date", ascending=False)
            edited_user_df = st.data_editor(display_df, num_rows="dynamic", use_container_width=True, key="editor")
            
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("💾 Save Changes"):
                    other_users_data = df_data[df_data["user"] != user]
                    edited_user_df["user"] = user
                    final_df = pd.concat([other_users_data, edited_user_df], ignore_index=True)
                    with st.spinner("Saving..."):
                        save_csv(final_df, DATA_FILE, "Edited History")
                    st.success("Saved!")
                    st.rerun()
            with col_b:
                # Backup Feature
                csv = df_data.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Download Backup", data=csv, file_name="fitness_backup.csv", mime="text/csv")
