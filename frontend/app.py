import streamlit as st
import requests

# ── Configuration ─────────────────────────────────────────────
# Updated to point directly to your live Render backend URL!
BACKEND = "https://expense-tracker-ai-zgkl.onrender.com" 

# ── Login screen ──────────────────────────────────────────────
if "user_id" not in st.session_state:
    st.session_state.user_id = None

if not st.session_state.user_id:
    st.title("Finance Bot")
    st.subheader("Enter your username to get started")

    username = st.text_input("Username", placeholder="e.g. rahul123")

    if st.button("Continue"):
        if username.strip() == "":
            st.error("Username cannot be empty.")
        else:
            try:
                res = requests.post(
                    f"{BACKEND}/register",
                    json={"user_id": username.strip()}
                )
                data = res.json()
                st.session_state.user_id = data["user_id"]

                if data["status"] == "created":
                    st.success(f"Welcome, {data['user_id']}! Account created.")
                else:
                    st.success(f"Welcome back, {data['user_id']}!")
                st.rerun()
            except Exception as e:
                st.error(f"Cannot connect to Backend Server. Make sure it is running! Error: {e}")

    st.stop()  # don't render anything below until logged in

# ── Main app (only reached after login) ───────────────────────
user_id = st.session_state.user_id

st.title("Finance Bot")
col1, col2 = st.columns([6, 1])
col1.caption(f"Logged in as **{user_id}**")
if col2.button("Logout"):
    st.session_state.user_id = None
    st.session_state.history = []
    st.rerun()

tab1, tab2 = st.tabs(["Chat", "History"])

# ── Tab 1: Chat ───────────────────────────────────────────────
with tab1:
    st.caption("Type any expense message and it will be classified automatically.")

    if "history" not in st.session_state:
        st.session_state.history = []

    user_input = st.chat_input("e.g. 350 for biryani at Mehfil")

    if user_input:
        with st.spinner("Classifying..."):
            try:
                res = requests.post(
                    f"{BACKEND}/classify",
                    json={
                        "user_id": user_id,
                        "text": user_input
                    }
                )
                result = res.json()
                st.session_state.history.append({
                    "message": user_input,
                    "result": result,
                    "error": None
                })
            except Exception as e:
                st.session_state.history.append({
                    "message": user_input,
                    "result": None,
                    "error": str(e)
                })

    for entry in reversed(st.session_state.history):
        with st.chat_message("user"):
            st.write(entry["message"])
        with st.chat_message("assistant"):
            if entry["error"]:
                st.error(f"Something went wrong: {entry['error']}")
            else:
                r = entry["result"]
                col1, col2, col3 = st.columns(3)
                col1.metric("Amount", f"References: ₹{r['amount']}" if r['amount'] else "—")
                col2.metric("Category", r['category'])
                col3.metric("Vendor", r['vendor'] or "—")
                st.caption(r['description'])

# ── Tab 2: History ────────────────────────────────────────────
with tab2:
    st.subheader("All transactions")

    if st.button("Refresh"):
        st.rerun()

    try:
        summary = requests.get(f"{BACKEND}/summary/{user_id}").json()
        if summary:
            cols = st.columns(len(summary))
            for i, item in enumerate(summary):
                cols[i].metric(
                    item["category"],
                    f"₹{item['total']:.0f}",
                    f"{item['count']} transactions"
                )

        st.divider()

        transactions = requests.get(f"{BACKEND}/transactions/{user_id}").json()
        if transactions:
            for t in transactions:
                with st.expander(f"{t['created_at']}  ·  {t['category']}  ·  ₹{t['amount'] or '?'}"):
                    st.write(f"**Message:** {t['message']}")
                    st.write(f"**Vendor:** {t['vendor'] or '—'}")
                    st.write(f"**Description:** {t['description']}")
        else:
            st.info("No transactions yet. Go to Chat and add some!")

    except Exception as e:
        st.error(f"Could not load transactions: {e}")