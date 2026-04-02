"""
Flashspace AI Agent — Comprehensive Test Dashboard
Run with: streamlit run test_dashboard.py
"""

import json
import time
import uuid
import requests
import streamlit as st

# ─────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Flashspace Agent — Test Dashboard",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────
# Styling
# ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
    [data-testid="stSidebar"] { background: #0f0f1a; }
    [data-testid="stSidebar"] * { color: #e2e8f0 !important; }
    .role-badge {
        display: inline-block; padding: 3px 10px; border-radius: 12px;
        font-size: 11px; font-weight: 700; letter-spacing: 0.5px; margin-bottom: 8px;
    }
    .badge-guest   { background:#1e3a5f; color:#93c5fd; }
    .badge-admin   { background:#3b1f1f; color:#fca5a5; }
    .badge-partner { background:#1f3b2a; color:#86efac; }
    .badge-affiliate { background:#2d1f3b; color:#c4b5fd; }
    .status-ok   { color: #22c55e; font-weight: 700; }
    .status-fail { color: #ef4444; font-weight: 700; }
    .status-warn { color: #f59e0b; font-weight: 700; }
    .info-box {
        background: #1e293b; border-left: 3px solid #3b82f6;
        padding: 10px 14px; border-radius: 6px; margin: 8px 0; font-size: 13px;
    }
    div[data-testid="stChatMessage"] { border-radius: 10px; margin-bottom: 6px; }
    .st-emotion-cache-1kyxreq { gap: 0.4rem; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# Known test tokens  (pre-loaded for convenience)
# ─────────────────────────────────────────────────────────────
KNOWN_TOKENS = {
    "admin":    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoidGVzdF91c2VyIiwidGVuYW50X2lkIjoidGVzdF90ZW5hbnQiLCJyb2xlIjoiYWRtaW4iLCJleHAiOjE4NDIwMzEyMzB9.4xNF97oOUCPoaniYixuKuTIfqja8SXBzj1Na9hQciRQ",
    "partner":  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoidGVzdF91c2VyIiwidGVuYW50X2lkIjoidGVzdF90ZW5hbnQiLCJyb2xlIjoicGFydG5lciIsImV4cCI6MTg0MjAzMTIzMH0.yKdc9wCCbPZS61DnFXa6wE0uDP7AsM5ww4VXFx4agkk",
    "affiliate":"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoidGVzdF91c2VyIiwidGVuYW50X2lkIjoidGVzdF90ZW5hbnQiLCJyb2xlIjoiYWZmaWxpYXRlIiwiZXhwIjoxODQyMDMxMjMwfQ.gOuGXlKPF8f-gl1M73dMO0_OvEgKRZtRqs1evoa8uew",
}

ROLE_INFO = {
    "guest":     {"badge": "badge-guest",     "emoji": "👤", "note": "No token required — public access",          "implemented": True},
    "admin":     {"badge": "badge-admin",     "emoji": "🔴", "note": "Full DB access, analytics, platform-wide",   "implemented": True},
    "partner":   {"badge": "badge-partner",   "emoji": "🟢", "note": "Own spaces, bookings, revenue (scoped)",      "implemented": True},
    "affiliate": {"badge": "badge-affiliate", "emoji": "🟣", "note": "⚠️ Token accepted but agent NOT yet built",  "implemented": False},
}

SAMPLE_QUERIES = {
    "guest": [
        "What coworking spaces do you have in Bangalore?",
        "Tell me about virtual office plans",
        "What is the price of a meeting room in Koramangala?",
        "Do you have spaces near Indiranagar?",
    ],
    "admin": [
        "How many users are registered on the platform?",
        "Show me total revenue this month",
        "List the top 5 partners by bookings",
        "How many bookings are active right now?",
        "What are your platform services?",
    ],
    "partner": [
        "Show my total revenue",
        "How many customers booked my spaces?",
        "What is my current booking status?",
        "Show me my invoices",
        "What services does Flashspace offer to partners?",
    ],
    "affiliate": [
        "What is my commission status?",
        "How many leads have I generated?",
    ],
}

# ─────────────────────────────────────────────────────────────
# Session state bootstrap
# ─────────────────────────────────────────────────────────────
def _fresh_chat():
    return {"messages": [], "conversation_id": f"conv_{uuid.uuid4().hex[:10]}", "session_id": f"sess_{uuid.uuid4().hex[:10]}"}

for _r in ROLE_INFO:
    if f"chat_{_r}" not in st.session_state:
        st.session_state[f"chat_{_r}"] = _fresh_chat()
    if f"token_{_r}" not in st.session_state:
        st.session_state[f"token_{_r}"] = KNOWN_TOKENS.get(_r, "")

if "active_tab" not in st.session_state:
    st.session_state.active_tab = "chat"

# ─────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🔬 Test Dashboard")
    st.markdown("---")

    backend = st.text_input("🌐 Backend URL", value="http://127.0.0.1:8002")
    st.markdown("---")

    role = st.radio(
        "Active Role",
        list(ROLE_INFO.keys()),
        format_func=lambda r: f"{ROLE_INFO[r]['emoji']} {r.title()}",
    )
    info = ROLE_INFO[role]
    st.markdown(f'<span class="role-badge {info["badge"]}">{role.upper()}</span>', unsafe_allow_html=True)
    st.caption(info["note"])

    st.markdown("---")

    # Token input
    if role != "guest":
        token_input = st.text_input(
            f"JWT Token ({role})",
            value=st.session_state[f"token_{role}"],
            type="password",
            help="Pre-loaded from tokens.txt. Override if needed."
        )
        st.session_state[f"token_{role}"] = token_input.strip()
        if token_input.strip():
            st.markdown('<span class="status-ok">✓ Token set</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="status-warn">⚠ No token — will be rejected</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="status-ok">✓ No token needed</span>', unsafe_allow_html=True)

    st.markdown("---")

    # Quick-fire test queries
    st.markdown("**⚡ Quick Test Queries**")
    for q in SAMPLE_QUERIES.get(role, []):
        if st.button(q[:45] + ("…" if len(q) > 45 else ""), key=f"quick_{hash(q)}"):
            st.session_state[f"pending_{role}"] = q

    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🧹 Clear Chat"):
            st.session_state[f"chat_{role}"] = _fresh_chat()
            st.rerun()
    with col2:
        if st.button("🔄 New Session"):
            st.session_state[f"chat_{role}"] = _fresh_chat()
            st.rerun()

    st.markdown("---")
    st.markdown(f"""
<div class="info-box">
<b>Session Info</b><br>
Conv: <code>{st.session_state[f"chat_{role}"]["conversation_id"]}</code><br>
Sess: <code>{st.session_state[f"chat_{role}"]["session_id"]}</code>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# Main area — Tabs
# ─────────────────────────────────────────────────────────────
tab_chat, tab_status, tab_debug = st.tabs(["💬 Chat", "📊 System Status", "🛠 Debug & Raw"])

# ── TAB 1: Chat ──────────────────────────────────────────────
with tab_chat:
    info = ROLE_INFO[role]
    st.markdown(
        f'<span class="role-badge {info["badge"]}">{info["emoji"]} {role.upper()} AGENT</span>',
        unsafe_allow_html=True
    )

    if not info["implemented"]:
        st.warning(
            f"⚠️ The **{role}** agent is not yet fully implemented in the backend. "
            "The JWT will authenticate but there is no routing logic for this role — "
            "you will likely get an error or no response from `/chat`.",
            icon="⚠️"
        )

    chat_state = st.session_state[f"chat_{role}"]

    # Render history
    chat_container = st.container()
    with chat_container:
        for msg in chat_state["messages"]:
            with st.chat_message(msg["role"]):
                if msg["role"] == "assistant":
                    is_error = msg.get("is_error", False)
                    if is_error:
                        st.error(msg["content"])
                    else:
                        st.markdown(msg["content"])
                else:
                    st.markdown(msg["content"])

    # Input
    user_input = st.chat_input(f"Message as {role}…")
    prompt = st.session_state.pop(f"pending_{role}", None) or user_input

    if prompt:
        chat_state["messages"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Build request
        headers = {"Content-Type": "application/json"}
        token = st.session_state.get(f"token_{role}", "").strip()
        if role != "guest" and token:
            headers["Authorization"] = f"Bearer {token}"

        payload = {
            "query": prompt,
            "conversation_id": chat_state["conversation_id"],
            "session_id": chat_state["session_id"],
        }

        start_t = time.time()
        reply = ""
        is_error = False
        raw_response = None
        status_code = None

        with st.spinner(f"Thinking as {role}…"):
            try:
                resp = requests.post(
                    f"{backend.rstrip('/')}/chat",
                    json=payload,
                    headers=headers,
                    timeout=120,
                )
                status_code = resp.status_code
                raw_response = resp.text
                elapsed = round(time.time() - start_t, 2)

                if resp.ok:
                    data = resp.json()
                    chat_state["session_id"] = (data.get("session_id") or chat_state["session_id"]).strip()
                    reply = data.get("reply") or data.get("error") or "⚠ Empty response from backend."
                else:
                    reply = f"HTTP {resp.status_code}: {resp.text[:500]}"
                    is_error = True

            except requests.ConnectionError:
                reply = f"❌ Cannot connect to backend at `{backend}`.\nMake sure `uvicorn app.main:app --reload` is running."
                is_error = True
                elapsed = round(time.time() - start_t, 2)
            except requests.Timeout:
                reply = "⏱ Request timed out (>120s). The backend may be overloaded."
                is_error = True
                elapsed = round(time.time() - start_t, 2)
            except Exception as e:
                reply = f"Unexpected error: {e}"
                is_error = True
                elapsed = round(time.time() - start_t, 2)

        chat_state["messages"].append({"role": "assistant", "content": reply, "is_error": is_error})

        with st.chat_message("assistant"):
            if is_error:
                st.error(reply)
            else:
                st.markdown(reply)
            st.caption(f"⏱ {elapsed}s  |  HTTP {status_code or 'N/A'}  |  role={role}")

        # Store raw for debug tab
        st.session_state["last_raw"] = {
            "role": role, "prompt": prompt, "payload": payload,
            "headers": {k: (v[:20] + "…" if k == "Authorization" and len(v) > 20 else v) for k, v in headers.items()},
            "status_code": status_code, "raw_response": raw_response,
            "elapsed_s": elapsed if 'elapsed' in dir() else None,
        }

# ── TAB 2: System Status ─────────────────────────────────────
with tab_status:
    st.subheader("System Status Check")
    st.caption("Click the button to run live checks against the backend.")

    if st.button("🔍 Run Status Checks", type="primary"):
        results = {}

        # Health check
        with st.spinner("Checking /health…"):
            try:
                r = requests.get(f"{backend.rstrip('/')}/health", timeout=5)
                results["backend"] = ("✅ Online", r.json(), r.elapsed.total_seconds())
            except Exception as e:
                results["backend"] = ("❌ Offline", str(e), None)

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### 🌐 Backend")
            status, detail, elapsed = results["backend"]
            st.markdown(f"**Status:** {status}")
            if elapsed:
                st.markdown(f"**Latency:** {elapsed:.3f}s")
            st.json(detail if isinstance(detail, dict) else {"error": detail})

        with col2:
            st.markdown("#### 🤖 LLM Provider")
            st.markdown("Cloudflare Workers AI via AI Gateway")
            st.markdown("Model: `@cf/meta/llama-3.3-70b-instruct-fp8-fast`")
            st.markdown("Fallback: Google Gemini `gemini-2.0-flash`")

        st.markdown("---")
        st.subheader("Role Implementation Status")

        cols = st.columns(4)
        role_status = [
            ("👤 Guest",     "✅ Done",    "Full RAG pipeline, city memory, service recommendations, safety guard"),
            ("🔴 Admin",     "✅ Done",    "DB query (PyMongo), company RAG, router chain, safety guard"),
            ("🟢 Partner",   "✅ Done",    "Scoped DB queries, partner Pinecone KB, query normalizer, guard"),
            ("🟣 Affiliate", "❌ Not built", "JWT auth works but no /chat routing logic or prompts for this role"),
        ]
        for col, (name, status, detail) in zip(cols, role_status):
            with col:
                color = "#22c55e" if "Done" in status else "#ef4444"
                st.markdown(f"**{name}**")
                st.markdown(f'<span style="color:{color}">{status}</span>', unsafe_allow_html=True)
                st.caption(detail)

        st.markdown("---")
        st.subheader("What Has Been Tested")
        test_results = [
            ("CF Gateway raw curl", "✅ PASSED", "Response: `CF OK`"),
            ("LLM init (ChatOpenAI → CF)", "✅ PASSED", "model=`@cf/meta/llama-3.3-70b-instruct-fp8-fast`"),
            ("Simple Guest invoke", "✅ PASSED", "Coherent coworking space answer returned"),
            ("Safety guard (`json_mode`)", "✅ PASSED", "`allowed=True, category='safe'`"),
            ("Router chain (db/company)", "✅ PASSED", "Both routes correct"),
            ("MongoDB data access (live)", "⚠️ Pending", "Test via this UI: Admin DB query or Partner self-query"),
            ("Guest full end-to-end", "⚠️ Pending", "Use the Chat tab above"),
            ("Admin full end-to-end", "⚠️ Pending", "Use the Chat tab above"),
            ("Partner full end-to-end", "⚠️ Pending", "Use the Chat tab above"),
        ]
        for name, status, note in test_results:
            color = "#22c55e" if "PASSED" in status else ("#f59e0b" if "Pending" in status else "#ef4444")
            st.markdown(
                f'<span style="color:{color}">{"●"}</span> **{name}** — `{status}` — {note}',
                unsafe_allow_html=True
            )

# ── TAB 3: Debug ─────────────────────────────────────────────
with tab_debug:
    st.subheader("🛠 Last Request Debug")

    last = st.session_state.get("last_raw")
    if not last:
        st.info("Send a message in the Chat tab to see the raw request/response here.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Request sent**")
            st.markdown(f"- Role: `{last['role']}`")
            st.markdown(f"- Prompt: `{last['prompt'][:100]}`")
            st.markdown("**Headers:**")
            st.json(last["headers"])
            st.markdown("**Payload:**")
            st.json(last["payload"])
        with col2:
            st.markdown("**Response received**")
            st.markdown(f"- HTTP Status: `{last['status_code']}`")
            st.markdown(f"- Elapsed: `{last.get('elapsed_s', 'N/A')}s`")
            st.markdown("**Raw body:**")
            raw = last.get("raw_response", "")
            try:
                st.json(json.loads(raw))
            except Exception:
                st.code(raw[:2000] if raw else "(empty)")

    st.markdown("---")
    st.subheader("🔑 Token Inspector")
    st.caption("Paste a JWT to decode its payload (no verification — just base64 decode).")
    raw_token = st.text_area("Paste JWT", height=80)
    if raw_token.strip():
        try:
            import base64
            parts = raw_token.strip().split(".")
            if len(parts) == 3:
                pad = parts[1] + "=" * (-len(parts[1]) % 4)
                decoded = json.loads(base64.urlsafe_b64decode(pad))
                st.json(decoded)
                exp = decoded.get("exp")
                if exp:
                    import datetime
                    expiry = datetime.datetime.fromtimestamp(exp)
                    now = datetime.datetime.now()
                    if expiry > now:
                        st.success(f"Token valid until {expiry.strftime('%Y-%m-%d %H:%M:%S')}")
                    else:
                        st.error(f"Token EXPIRED at {expiry.strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception as e:
            st.error(f"Could not decode: {e}")
