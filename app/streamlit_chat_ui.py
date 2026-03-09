import requests
import streamlit as st
from uuid import uuid4


st.set_page_config(page_title="AI Agent Chat", page_icon="💬", layout="centered")

ROLE_OPTIONS = ("guest", "admin", "partner")


def _new_chat_state() -> dict:
    return {
        "messages": [],
        "conversation_id": f"conv_{uuid4().hex[:12]}",
        "session_id": f"sess_{uuid4().hex[:12]}",
    }


if "chat_state_by_role" not in st.session_state:
    st.session_state.chat_state_by_role = {role: _new_chat_state() for role in ROLE_OPTIONS}
if "selected_role" not in st.session_state:
    st.session_state.selected_role = "guest"
if "jwt_by_role" not in st.session_state:
    st.session_state.jwt_by_role = {"admin": "", "partner": ""}


with st.sidebar:
    st.header("Connection")
    base_url = st.text_input("Backend URL", value="http://127.0.0.1:8001")
    role = st.selectbox("Role", ROLE_OPTIONS, index=ROLE_OPTIONS.index(st.session_state.selected_role))
    st.session_state.selected_role = role

    if role in ("admin", "partner"):
        jwt_value = st.text_input(
            f"{role.title()} JWT",
            value=st.session_state.jwt_by_role.get(role, ""),
            type="password",
        )
        st.session_state.jwt_by_role[role] = jwt_value.strip()
    else:
        st.caption("Guest mode uses no Authorization header.")

    role_state = st.session_state.chat_state_by_role[role]
    st.text_input("Conversation ID", value=role_state["conversation_id"], disabled=True)
    st.text_input("Session ID", value=role_state["session_id"], disabled=True)

    if st.button("✨ find my space"):
        # Inject a trigger message to start the Find My Fit flow
        st.session_state.pending_query = "I'm not sure which service I need. Can you help me find my fit?"
        st.rerun()

    if st.button("Clear Chat (Current Role)"):
        st.session_state.chat_state_by_role[role] = _new_chat_state()
        st.rerun()


st.title(f"AI Agent Chat ({role.title()})")
role_state = st.session_state.chat_state_by_role[role]

for msg in role_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"], unsafe_allow_html=True)


# Always render the chat input so it doesn't disappear from the UI
user_input = st.chat_input("Type your message...")

# Determine the prompt: either from the "Help Me Choose" button or the input box
prompt = st.session_state.pop("pending_query", None) or user_input


if prompt:
    role_state["messages"].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    payload = {
        "query": prompt,
        "conversation_id": role_state["conversation_id"],
        "session_id": role_state["session_id"],
    }

    headers = {"Content-Type": "application/json"}
    if role in ("admin", "partner"):
        token = st.session_state.jwt_by_role.get(role, "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"

    try:
        response = requests.post(
            f"{base_url.rstrip('/')}/chat",
            json=payload,
            headers=headers,
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        role_state["session_id"] = (data.get("session_id") or role_state["session_id"]).strip()
        reply = data.get("reply") or data.get("error") or "No response received."
    except requests.RequestException as exc:
        reply = f"Request failed: {exc}"

    role_state["messages"].append({"role": "assistant", "content": reply})
    with st.chat_message("assistant"):
        st.markdown(reply, unsafe_allow_html=True)
