# * Streamlit chat UI. Talks to the API over HTTP. Run: streamlit run ui/app.py
import httpx
import streamlit as st

from unirag.config.settings import get_settings

API = get_settings().api_url
# * The pipeline can take several LLM calls; give it time.
TIMEOUT_S = 120

st.set_page_config(page_title="UniRAG", page_icon="🎓")
st.title("UniRAG: ask about AIT")
st.caption("A fictional university. All data is synthetic.")


def load_roles() -> list[dict]:
    try:
        return httpx.get(f"{API}/roles", timeout=10).json()
    except httpx.HTTPError:
        st.error(f"Cannot reach the API at {API}. Start it with: uvicorn unirag.api.app:app")
        st.stop()


roles = load_roles()
labels = {r["id"]: r["id"] if r["id"] == "guest" else f"{r['id']}: {r['label']}" for r in roles}
labels["guest"] = "Guest / Applicant"
role = st.sidebar.selectbox("Who is asking?", list(labels), format_func=labels.get)
st.sidebar.caption("No login: the role only decides which records the answers may use.")

# * One chat history per role, so switching role never shows another student's answers.
history: list[dict] = st.session_state.setdefault(f"chat_{role}", [])


def show(reply: dict) -> None:
    st.markdown(reply["text"])
    for c in reply["citations"]:
        where = (
            f"{c['document']} > {c['heading']}"
            if c["kind"] == "document"
            else ", ".join(c["tables"])
        )
        st.caption(f"[{c['label']}] {where}")
    with st.expander("Details"):
        st.write(f"Route: `{reply['route']}` · Status: `{reply['status']}`")
        if reply["missing"]:
            st.write("Missing: " + ", ".join(reply["missing"]))
        if reply["sql"]:
            st.code(reply["sql"], language="sql")
            table = [dict(zip(reply["columns"], row, strict=True)) for row in reply["rows"]]
            st.dataframe(table, hide_index=True)
        st.write({"latency_s": reply["latency_s"], "tokens": reply["tokens"]})


for turn in history:
    with st.chat_message(turn["who"]):
        show(turn["reply"]) if turn["who"] == "assistant" else st.markdown(turn["text"])

if question := st.chat_input("Ask a question"):
    history.append({"who": "user", "text": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"), st.spinner("Thinking..."):
        try:
            response = httpx.post(
                f"{API}/chat", json={"question": question, "role": role}, timeout=TIMEOUT_S
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            st.error(f"The API call failed: {e}")
            st.stop()
        reply = response.json()
        show(reply)
    history.append({"who": "assistant", "reply": reply})
