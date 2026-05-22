import streamlit as plt
import requests

# Set this to your actual Render live URL!
BACKEND_URL = "https://expense-tracker-ai-7eerztczkrhxvpngs6zdsz.onrender.com" 

plt.set_page_config(page_title="AI Expense Tracker", layout="wide")
plt.title("💰 Personal AI Expense Tracker")

if "user_id" not in plt.session_state:
    plt.session_state.user_id = ""
if "logged_in" not in plt.session_state:
    plt.session_state.logged_in = False

# ── Login View ────────────────────────────────────────────────
if not plt.session_state.logged_in:
    user_input = plt.text_input("Enter your unique Username:", value=plt.session_state.user_id)
    if plt.button("Log In / Register"):
        if user_input.strip():
            try:
                res = requests.post(f"{BACKEND_URL}/register", json={"user_id": user_input.strip().lower()})
                if res.status_code == 200:
                    plt.session_state.user_id = user_input.strip().lower()
                    plt.session_state.logged_in = True
                    plt.rerun()
                else:
                    plt.error("Could not register user with backend.")
            except Exception as e:
                plt.error(f"Backend connection error: {e}")
        else:
            plt.warning("Username cannot be empty.")

# ── Main Dashboard View ───────────────────────────────────────
else:
    plt.sidebar.write(f"Logged in as: **{plt.session_state.user_id}**")
    if plt.sidebar.button("Log Out"):
        plt.session_state.logged_in = False
        plt.session_state.user_id = ""
        plt.rerun()

    # 1. Main Chat Interface Entry Box
    message = plt.text_input("Type any expense message and it will be classified automatically.", placeholder="e.g. 350 for biryani at Mehfil")
    
    if plt.button("Send ✨", rekey="send_btn") or (message and plt.session_state.get("last_msg") != message):
        if message:
            plt.session_state["last_msg"] = message
            with plt.spinner("AI is processing your transaction..."):
                try:
                    res = requests.post(
                        f"{BACKEND_URL}/classify", 
                        json={"user_id": plt.session_state.user_id, "text": message}
                    )
                    if res.status_code == 200:
                        r = res.json()
                        plt.success("Transaction logged successfully!")
                        
                        # Fixes KeyError crashes by using safe dictionary .get() methods
                        col1, col2, col3 = plt.columns(3)
                        amount_val = r.get("amount")
                        vendor_val = r.get("vendor") or "Unknown"
                        category_val = r.get("category") or "Other"

                        if amount_val is not None:
                            col1.metric("Amount", f"₹{amount_val}")
                        else:
                            col1.metric("Amount", "—")
                            
                        col2.metric("Vendor", str(vendor_val).title())
                        col3.metric("Category", str(category_val).title())
                    else:
                        plt.error(f"Error: {res.json().get('detail', 'Unknown error classification failure')}")
                except Exception as e:
                    plt.error(f"Could not reach backend service: {e}")

    plt.markdown("---")

    # 2. History & Summary Dashboard Charts Layout
    try:
        history_res = requests.get(f"{BACKEND_URL}/transactions/{plt.session_state.user_id}")
        summary_res = requests.get(f"{BACKEND_URL}/summary/{plt.session_state.user_id}")
        
        tab1, tab2 = plt.tabs(["📋 History Log", "📊 Spending Summary"])
        
        with tab1:
            if history_res.status_code == 200 and history_res.json():
                plt.dataframe(history_res.json(), use_container_width=True)
            else:
                plt.info("No logs added yet! Send an expense message above.")
                
        with tab2:
            if summary_res.status_code == 200 and summary_res.json():
                summary_data = summary_res.json()
                plt.write("### Category Breakdown")
                for item in summary_data:
                    plt.write(f"- **{item['category']}**: ₹{item['total']:.2f} ({item['count']} transactions)")
            else:
                plt.info("No summaries available.")
    except Exception as e:
        plt.write("Dashboard tables temporarily unavailable.")