"""Streamlit chat UI for Keystone.

Features:
- User switcher to act as any seeded employee
- Chat with cited sources
- Approval panel for pending write actions
- Audit log view with Langfuse trace links
- Side-by-side demo mode
"""

import os

import httpx
import streamlit as st

API_URL = os.environ.get("API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Keystone - Meridian Freight AI",
    page_icon="🔑",
    layout="wide",
)

# --- Session State Init ---
if "token" not in st.session_state:
    st.session_state.token = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_user" not in st.session_state:
    st.session_state.current_user = None
if "demo_mode" not in st.session_state:
    st.session_state.demo_mode = False


def api_call(method: str, path: str, **kwargs) -> httpx.Response | None:
    """Make an API call with auth token."""
    headers = {}
    if st.session_state.token:
        headers["Authorization"] = f"Bearer {st.session_state.token}"
    try:
        client = httpx.Client(base_url=API_URL, timeout=30)
        resp = client.request(method, path, headers=headers, **kwargs)
        return resp
    except Exception as e:
        st.error(f"API error: {e}")
        return None


def login(username: str) -> bool:
    """Login as a demo user."""
    resp = api_call("POST", "/auth/login", json={"username": username})
    if resp and resp.status_code == 200:
        data = resp.json()
        st.session_state.token = data["token"]
        st.session_state.current_user = data
        st.session_state.messages = []
        return True
    return False


# --- Sidebar: User Switcher ---
with st.sidebar:
    st.title("🔑 Keystone")
    st.caption("Permission-aware AI for Meridian Freight")

    st.divider()
    st.subheader("User Switcher")

    demo_users = {
        "ceo": "CEO (Executive)",
        "vp_sales": "VP Sales (Executive)",
        "cfo": "CFO (Executive)",
        "cto": "CTO (Executive)",
        "vp_people": "VP People (Executive)",
        "sales_manager": "Sales Manager",
        "ops_manager": "Ops Manager",
        "hr_partner": "HR Business Partner",
        "finance_analyst": "Financial Analyst",
        "sales_rep": "Account Executive",
        "engineer": "Software Engineer (IC)",
        "contractor": "Contract Developer",
    }

    selected_user = st.selectbox(
        "Login as:",
        options=list(demo_users.keys()),
        format_func=lambda x: demo_users[x],
        key="user_select",
    )

    if st.button("Switch User", use_container_width=True):
        if login(selected_user):
            st.success(f"Logged in as {demo_users[selected_user]}")
            st.rerun()
        else:
            st.error("Login failed")

    if st.session_state.current_user:
        st.divider()
        user = st.session_state.current_user
        st.metric("Role", user.get("role", "?"))
        st.caption(f"Employee ID: {user.get('employee_id', '?')}")

    st.divider()

    # Demo mode toggle
    st.session_state.demo_mode = st.toggle("Side-by-Side Demo", value=st.session_state.demo_mode)

    # Audit log link
    if st.button("View Audit Log", use_container_width=True):
        st.session_state.show_audit = True

    st.divider()
    st.caption("Built with LangGraph + Cerbos + Postgres RLS")

# --- Main Content ---
if not st.session_state.token:
    st.title("Welcome to Keystone")
    st.info("Select a user from the sidebar and click 'Switch User' to begin.")
    st.markdown("""
    ### About Keystone
    Keystone is a permission-aware AI agent for **Meridian Freight**, a fictional 120-person logistics company.

    **The agent enforces permissions at every layer:**
    1. **Policy Engine** (Cerbos) — checks permissions before each tool call
    2. **Database** (Postgres RLS) — filters rows at the SQL level
    3. **Input Guard** — detects prompt injection in retrieved content
    4. **Output Scanner** — blocks responses containing unauthorized canary strings

    ### Try These Scenarios
    - 🔑 **Executive**: "Show me the board minutes" → See confidential acquisition discussion
    - 👷 **Contractor**: "Show me the board minutes" → Access denied
    - 💰 **HR Partner**: "What is employee 20's salary?" → Full access
    - 🔒 **Engineer**: "What is the CEO's salary?" → Denied
    """)
    st.stop()

# --- Chat Interface ---
if not st.session_state.demo_mode:
    st.title("Keystone Chat")

    # Display message history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("sources"):
                with st.expander("Sources"):
                    for s in msg["sources"]:
                        st.caption(f"[{s['type']}] {s['id']}: {s.get('title', '')}")
            if msg.get("trace_id"):
                st.caption(f"Trace: {msg['trace_id']}")

    # Chat input
    if prompt := st.chat_input("Ask Keystone..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"), st.spinner("Thinking..."):
            resp = api_call("POST", "/chat", json={"message": prompt})
            if resp and resp.status_code == 200:
                data = resp.json()
                reply = data.get("reply", "No response")
                sources = data.get("sources", [])
                trace_id = data.get("trace_id")
                pending = data.get("pending_actions", [])

                st.markdown(reply)

                if sources:
                    with st.expander("Sources"):
                        for s in sources:
                            st.caption(f"[{s['type']}] {s['id']}: {s.get('title', '')}")

                if trace_id:
                    st.caption(f"Trace: {trace_id}")

                # Approval panel for pending actions
                if pending:
                    st.warning("⚠️ Action requires your approval:")
                    for action in pending:
                        st.json(action)
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("✅ Approve", key=f"approve_{trace_id}"):
                                st.success("Action approved")
                        with col2:
                            if st.button("❌ Deny", key=f"deny_{trace_id}"):
                                st.info("Action denied")

                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": reply,
                        "sources": sources,
                        "trace_id": trace_id,
                    }
                )
            else:
                error = "Failed to get response"
                if resp:
                    error = resp.text
                st.error(error)
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": f"Error: {error}",
                    }
                )

else:
    # --- Side-by-Side Demo Mode ---
    st.title("Side-by-Side Demo")
    st.info("The same question asked as three different roles. See how permissions change the response.")

    demo_question = st.text_input(
        "Enter a question:",
        value="Show me the board meeting minutes about the acquisition",
    )

    demo_roles = [
        ("contractor", "Contractor"),
        ("sales_manager", "Sales Manager"),
        ("ceo", "CEO (Executive)"),
    ]

    if st.button("Run Demo", use_container_width=True):
        cols = st.columns(3)
        for col, (username, label) in zip(cols, demo_roles):
            with col:
                st.subheader(label)
                # Login as this user
                login_resp = api_call("POST", "/auth/login", json={"username": username})
                if login_resp and login_resp.status_code == 200:
                    token = login_resp.json()["token"]
                    # Ask the question
                    headers = {"Authorization": f"Bearer {token}"}
                    try:
                        client = httpx.Client(base_url=API_URL, timeout=30)
                        chat_resp = client.post(
                            "/chat",
                            json={"message": demo_question},
                            headers=headers,
                        )
                        if chat_resp.status_code == 200:
                            data = chat_resp.json()
                            st.markdown(data.get("reply", "No response"))
                            if data.get("sources"):
                                st.caption(f"Sources: {len(data['sources'])}")
                        else:
                            st.error(f"Error: {chat_resp.status_code}")
                    except Exception as e:
                        st.error(str(e))
                else:
                    st.error("Login failed")

        # Restore original session
        if st.session_state.current_user:
            login(selected_user)

# --- Audit Log View ---
if st.session_state.get("show_audit"):
    st.divider()
    st.subheader("Audit Log")
    resp = api_call("GET", "/audit?limit=20")
    if resp and resp.status_code == 200:
        entries = resp.json()
        if entries:
            for entry in entries:
                with st.expander(f"{entry['timestamp']} — {entry['tool']} ({entry['result_status']})"):
                    st.json(entry)
        else:
            st.info("No audit log entries yet")
    st.session_state.show_audit = False
