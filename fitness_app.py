import streamlit as st
import pandas as pd
from datetime import datetime, date
from github import Github
import io
import plotly.express as px
import google.generativeai as genai
from PIL import Image

# --- Configuration ---
REPO_NAME = "badinlee/sister-fitness"  # <--- UPDATE THIS
DATA_FILE = "data.csv"
PROFILE_FILE = "profiles.csv"

# --- Setup Google AI (Vision) ---
if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
else:
    st.error("Missing Google API Key in Secrets!")

# --- Helper Functions (Same as before) ---
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

# --- AI Logic ---
def get_calories_from_photo(image_data):
    """Sends photo to Gemini AI and asks for calorie estimate"""
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = (
            "Analyze this food image. Identify the food item and estimate the total calories. "
            "Return ONLY a string in this exact format: 'Food Name|Calories'. "
            "Example: 'Slice of Pizza|280'. If not food, return 'Error|0'."
        )
        response = model.generate_content([prompt, image_data])
        text = response.text.strip()
        name, cals = text.split('|')
        return name, int(cals)
    except Exception as e:
        return "Could not identify", 0

# --- App Layout ---
st.set_page_config(page_title="SisFit Vision", page_icon="👁️", layout="centered")
st.title("👁️ Sister Fitness Vision")

user = st.sidebar.selectbox("User", ["Me", "Sister"])
df_data = load_csv(DATA_FILE)
df_profiles = load_csv(PROFILE_FILE)

# (Profile check logic hidden for brevity - assumes profile exists. 
# If you deleted your profile, run the previous code once to recreate it!)

if not df_profiles.empty:
    user_profile = df_profiles[df_profiles["user"] == user].iloc[0]
    
    # --- DASHBOARD METRICS ---
    today_str = datetime.now().strftime("%Y-%m-%d")
    calories_today = 0
    if not df_data.empty:
        df_data["date_str"] = pd.to_datetime(df_data["date"]).dt.strftime("%Y-%m-%d")
        calories_today = df_data[(df_data["user"]==user) & (df_data["date_str"]==today_str)]["calories"].sum()
    
    goal = int(user_profile["calorie_target"])
    col1, col2 = st.columns(2)
    col1.metric("Today's Calories", int(calories_today), f"Goal: {goal}")
    col2.metric("Remaining", goal - int(calories_today))

    # --- MAIN TABS ---
    st.divider()
    tab1, tab2, tab3 = st.tabs(["📸 Snap Food", "📝 Text Log", "📊 History"])

    # --- TAB 1: AI CAMERA ---
    with tab1:
        st.subheader("AI Calorie Scanner")
        enable_cam = st.checkbox("Open Camera")
        
        img_file_buffer = None
        if enable_cam:
            img_file_buffer = st.camera_input("Take a picture of your meal")

        if img_file_buffer is not None:
            # Show the "Analyzing" spinner
            with st.spinner("🤖 AI is looking at your food..."):
                # Convert to format AI needs
                image = Image.open(img_file_buffer)
                food_name, food_cals = get_calories_from_photo(image)
            
            if food_cals > 0:
                st.success(f"I found: **{food_name}** (~{food_cals} cals)")
                
                # Verify before adding
                with st.form("confirm_ai"):
                    final_name = st.text_input("Food Name", value=food_name)
                    final_cals = st.number_input("Calories", value=food_cals)
                    if st.form_submit_button("✅ Add to Log"):
                        new_entry = {
                            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "user": user,
                            "weight": df_data[df_data["user"]==user].iloc[-1]["weight"] if not df_data.empty else user_profile["start_weight"],
                            "calories": final_cals,
                            "notes": f"📸 {final_name}"
                        }
                        updated_data = pd.concat([df_data, pd.DataFrame([new_entry])], ignore_index=True)
                        save_csv(updated_data, DATA_FILE, f"AI Log: {final_name}")
                        st.success("Logged!")
                        st.rerun()
            else:
                st.error("Couldn't identify food. Try entering manually in the Text Log tab.")

    # --- TAB 2: MANUAL LOG (Simplified) ---
    with tab2:
        with st.form("manual"):
            txt_desc = st.text_input("Food Name")
            txt_cals = st.number_input("Calories", min_value=0)
            if st.form_submit_button("Add"):
                new_entry = {
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "user": user,
                    "weight": 70, # Placeholder
                    "calories": txt_cals,
                    "notes": txt_desc
                }
                updated_data = pd.concat([df_data, pd.DataFrame([new_entry])], ignore_index=True)
                save_csv(updated_data, DATA_FILE, "Manual Log")
                st.rerun()

    # --- TAB 3: HISTORY ---
    with tab3:
        if not df_data.empty:
            st.dataframe(df_data[df_data["user"]==user].tail(10))
