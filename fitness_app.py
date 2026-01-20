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

# --- YOUR DATA (From Documents) ---
SHOPPING_LIST = {
    "Produce": ["Spinach/Salad Mix", "Frozen Mixed Berries (Large)", "Avocados (3-4)", "Fruit (10 pieces)", "Frozen Veg (4 bags)", "Courgettes", "Garlic & Ginger"],
    "Butchery": ["Chicken Breast (3kg)", "Eggs (1 Dozen)", "Anchor Protein+ Yogurt (2kg)", "Cheese (500g Edam/Tasty)"],
    "Pantry": ["Vogel's Bread", "Bagel Thins (Rebel)", "Rice Cups (6-8) or 1kg Bag", "Salsa (F. Whitlock's)", "Oil Spray", "Mayo/Soy/Honey/Sriracha", "Spices (Paprika, Garlic, Cajun)"]
}

# Pre-calculated Meal Plan
MY_MENU = {
    "Breakfast (Standard)": {"cals": 400, "desc": "220g Yogurt + 100g Berries + 25g Nuts"},
    "Breakfast (Toast Option)": {"cals": 400, "desc": "2 Vogel's + 75g Avo + 1 Egg"},
    "Snack (Bridge)": {"cals": 250, "desc": "Fruit + Protein Shake/Coffee"},
    "Dinner A (Stir-Fry)": {"cals": 1000, "desc": "Honey Soy Chicken (300g) + 1.5 cups Rice + Veg"},
    "Dinner B (Burger)": {"cals": 1000, "desc": "Double Chicken Burger (250g) + Wedges"},
    "Dinner C (Mexican)": {"cals": 1000, "desc": "Mexican Bowl (300g Chicken + Rice + Avo)"}
}

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
            "1. If it's a barcode/label: Extract product name and calories per serving. "
            "2. If it's a meal: Estimate calories. "
            "Return ONLY a string: 'Food Name|Calories'. Example: 'Oat Bar|180'. "
            "If unknown, return 'Unknown|0'."
        )
        response = model.generate_content([prompt, image_data])
        text = response.text.strip()
        if '|' in text:
            name, cals = text.split('|')
            return name, int(cals)
        return "Unknown Item", 0
    except:
        return "Error analyzing", 0

def ask_ai_chef(query, calories_left, ingredients):
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        # We feed the AI your specific shopping list so it suggests things you actually have!
        prompt = f"""
        I have {calories_left} calories left. 
        My available ingredients are: {ingredients}.
        The user asks: '{query}'.
        Suggest a recipe or snack using ONLY my ingredients if possible.
        """
        response = model.generate_content(prompt)
        return response.text
    except:
        return "Chef is busy."

# --- App Layout ---
st.set_page_config(page_title="SisFit Life", page_icon="🥗", layout="centered")
st.title("🥗 Sister Fitness Life")

user = st.sidebar.selectbox("User", ["Me", "Sister"])
df_data = load_csv(DATA_FILE)
df_profiles = load_csv(PROFILE_FILE)

# --- REPAIR DATA ---
if not df_data.empty:
    for col in ["meal_type", "notes"]:
        if col not in df_data.columns: df_data[col] = ""
    if "calories" not in df_data.columns: df_data[col] = 0
    if "weight" not in df_data.columns: df_data[col] = 0.0

if not df_profiles.empty:
    user_profile = df_profiles[df_profiles["user"] == user].iloc[0]
    
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

    # --- TABS (Reordered for Speed) ---
    st.divider()
    # "Quick Log" is first now!
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["⚡ Quick Log", "🛒 Shopping", "👨‍🍳 Chef", "📊 Stats", "✏️ Edit"])

    meal_options = ["Breakfast", "Lunch", "Dinner", "Snack"]
    current_hour = datetime.now().time()

    # --- TAB 1: QUICK LOG (One-Tap & Scan) ---
    with tab1:
        st.subheader("What are you eating?")
        
        # SECTION A: THE ONE-TAP MENU
        st.caption("👇 Tap your meal plan to add instantly")
        c1, c2 = st.columns(2)
        
        # Display buttons for your specific meals
        for i, (name, details) in enumerate(MY_MENU.items()):
            col = c1 if i % 2 == 0 else c2
            if col.button(f"➕ {name} ({details['cals']})"):
                log_dt = datetime.combine(date.today(), current_hour)
                new_entry = {
                    "date": log_dt.strftime("%Y-%m-%d %H:%M"),
                    "user": user, "weight": latest_weight, 
                    "calories": details['cals'], "notes": details['desc'], 
                    "meal_type": "Dinner" if "Dinner" in name else "Breakfast"
                }
                updated_data = pd.concat([df_data, pd.DataFrame([new_entry])], ignore_index=True)
                save_csv(updated_data, DATA_FILE, f"Quick Add: {name}")
                st.success(f"Added {name}!")
                st.rerun()

        st.divider()
        
        # SECTION B: THE SCANNER
        st.caption("📸 Or scan something new")
        enable_cam = st.checkbox("Open Camera")
        if enable_cam:
            img_file_buffer = st.camera_input("Snap Barcode/Food")
            if img_file_buffer is not None:
                with st.spinner("Analyzing..."):
                    image = Image.open(img_file_buffer)
                    food_name, food_cals = analyze_image(image)
                
                st.success(f"Found: **{food_name}** ({food_cals} cals)")
                with st.form("quick_scan_confirm"):
                    # Pre-filled form
                    q_name = st.text_input("Name", value=food_name)
                    q_cals = st.number_input("Calories", value=food_cals)
                    q_type = st.selectbox("Type", meal_options, index=3) # Default to Snack
                    
                    if st.form_submit_button("✅ Add It"):
                        log_dt = datetime.combine(date.today(), current_hour)
                        new_entry = {
                            "date": log_dt.strftime("%Y-%m-%d %H:%M"),
                            "user": user, "weight": latest_weight, 
                            "calories": q_cals, "notes": q_name, 
                            "meal_type": q_type
                        }
                        updated_data = pd.concat([df_data, pd.DataFrame([new_entry])], ignore_index=True)
                        save_csv(updated_data, DATA_FILE, f"Scanned: {q_name}")
                        st.rerun()

    # --- TAB 2: SHOPPING LIST ---
    with tab2:
        st.subheader("🛒 Master Shopping List")
        st.info("Your 'No Lunch' shopping list. Check items off as you go.")
        
        for category, items in SHOPPING_LIST.items():
            st.write(f"**{category}**")
            for item in items:
                st.checkbox(item, key=item) # Simple checkboxes
        
        st.caption("*Note: Checkboxes reset when you refresh the page.*")

    # --- TAB 3: AI CHEF ---
    with tab3:
        st.subheader("👨‍🍳 Kitchen Assistant")
        st.write("I know what ingredients you have in the pantry.")
        
        chef_query = st.text_input("Ask me (e.g., 'What can I make with the courgettes?')")
        if st.button("Ask Chef"):
            # Flatten shopping list to string for AI context
            all_ingredients = ", ".join([i for cat in SHOPPING_LIST.values() for i in cat])
            left = goal - int(calories_today)
            
            answer = ask_ai_chef(chef_query, left, all_ingredients)
            st.success(answer)

    # --- TAB 4: STATS ---
    with tab4:
        st.subheader("📊 Progress")
        if not df_data.empty:
            # Comparison Chart
            fig = px.line(df_data, x="date", y="weight", color="user", markers=True, title="Weight vs Sister")
            st.plotly_chart(fig)
            
            # Show history table
            st.dataframe(user_history[["date", "notes", "calories"]].sort_values("date", ascending=False).head(5), hide_index=True)

    # --- TAB 5: EDITOR ---
    with tab5:
        st.subheader("✏️ Fix Mistakes")
        if not user_history.empty:
            editable_cols = ["date", "weight", "calories", "notes", "meal_type"]
            display_df = user_history[editable_cols].sort_values("date", ascending=False)
            edited_user_df = st.data_editor(display_df, num_rows="dynamic", use_container_width=True, key="editor")
            
            if st.button("💾 Save Fixes"):
                other_users_data = df_data[df_data["user"] != user]
                edited_user_df["user"] = user
                final_df = pd.concat([other_users_data, edited_user_df], ignore_index=True)
                with st.spinner("Saving..."):
                    save_csv(final_df, DATA_FILE, "Edited History")
                st.success("Saved!")
                st.rerun()
