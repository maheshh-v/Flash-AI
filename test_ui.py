import streamlit as st
import requests
import json
import os

# Configuration
BACKEND_URL = "http://localhost:8000"  # Adjust if your backend runs on a different port

st.set_page_config(page_title="FlashSpace API Tester", layout="wide")

st.title("🚀 FlashSpace Multi-Role Tester")
st.markdown("Test Guest, Admin, and Partner roles independently.")

# Load tokens from tokens.txt
def load_tokens():
    tokens = {}
    tokens_file = "tokens.txt"
    if os.path.exists(tokens_file):
        with open(tokens_file, "r") as f:
            for line in f:
                if ":" in line:
                    role, token = line.strip().split(":", 1)
                    tokens[role.upper()] = token
    return tokens

TOKENS = load_tokens()

# Sidebar for configuration
with st.sidebar:
    st.header("Configuration")
    role = st.selectbox("Select Role", ["GUEST", "ADMIN", "PARTNER"])
    
    conv_id = st.text_input("Conversation ID", value="test_conv_1")
    session_id = st.text_input("Session ID (Optional)", value="")
    
    st.divider()
    if role != "GUEST":
        token = TOKENS.get(role, "")
        if token:
            st.success(f"Token loaded for {role}")
        else:
            st.error(f"No token found for {role} in tokens.txt")
            token = st.text_area("Manual Token Entry")
    else:
        st.info("Guest mode: No token required")
        token = None

# Chat interface
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# User input
if prompt := st.chat_input("What is your question?"):
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Prepare request
    endpoint = f"{BACKEND_URL}/{role.lower()}"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    payload = {
        "query": prompt,
        "conversation_id": conv_id
    }
    if session_id:
        payload["session_id"] = session_id

    # Call backend
    try:
        with st.chat_message("assistant"):
            with st.spinner(f"Calling {role} endpoint..."):
                response = requests.post(endpoint, json=payload, headers=headers)
                
                if response.status_code == 200:
                    data = response.json()
                    reply = data.get("reply", "No reply field in response")
                    st.markdown(reply)
                    
                    # Debug info in expander
                    with st.expander("Raw Response Details"):
                        st.json(data)
                        
                    st.session_state.messages.append({"role": "assistant", "content": reply})
                else:
                    error_msg = f"Error {response.status_code}: {response.text}"
                    st.error(error_msg)
                    st.session_state.messages.append({"role": "assistant", "content": error_msg})
    except Exception as e:
        st.error(f"Connection failed: {e}")

# Option to clear chat
if st.sidebar.button("Clear Chat"):
    st.session_state.messages = []
    st.rerun()
