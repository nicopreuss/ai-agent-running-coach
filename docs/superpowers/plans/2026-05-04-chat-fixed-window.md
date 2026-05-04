# Chat Fixed Window Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the Streamlit chat panel to a scrollable 650 px window so the page never scrolls and the input box is always visible.

**Architecture:** Two targeted edits to `ui/app.py` — a CSS snippet injected at page load to suppress Streamlit's outer padding and page scrollbar, and a `st.container(height=650)` wrapping the message loop in `_render_chat()`. A zero-height `st.components.v1.html` call scrolls the container to the bottom after each rerun.

**Tech Stack:** Python 3.11, Streamlit ≥ 1.35, `streamlit.components.v1`

---

## Files

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `ui/app.py` | CSS injection + `_render_chat()` refactor |

No new files. No other files touched.

---

### Task 1: Inject CSS to suppress page overflow

**Files:**
- Modify: `ui/app.py:156-160` (between `st.set_page_config` and `st.title`)

This removes Streamlit's default bottom padding on the main block container and hides the outer page scrollbar. Without it, the page may still show a scrollbar even after the chat window is fixed.

- [ ] **Step 1: Add the CSS block**

In `ui/app.py`, after `st.set_page_config(...)` and before `st.title(...)`, insert:

```python
st.markdown(
    """
    <style>
    .main > .block-container { padding-bottom: 0rem; }
    section.main { overflow: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)
```

The full layout section should now read:

```python
st.set_page_config(page_title="Running Coach", layout="wide")

st.markdown(
    """
    <style>
    .main > .block-container { padding-bottom: 0rem; }
    section.main { overflow: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Running Coach")
```

- [ ] **Step 2: Visual check**

Run the app:
```bash
poetry run streamlit run ui/app.py
```

Open `http://localhost:8501`. With no messages yet, confirm:
- No vertical scrollbar on the outer page
- The layout looks unchanged otherwise (title, sidebar, two columns still present)

- [ ] **Step 3: Commit**

```bash
git add ui/app.py
git commit -m "feat: inject CSS to suppress page overflow in chat layout"
```

---

### Task 2: Wrap message loop in fixed-height container with auto-scroll

**Files:**
- Modify: `ui/app.py:105-153` (`_render_chat()` function)

`st.container(height=650)` renders a fixed-height div with internal scroll. The message `for` loop moves inside it. A zero-height `st.components.v1.html` call after the container injects JS that scrolls it to the bottom — `st.markdown` does not execute `<script>` tags (React's `innerHTML` skips them), so `components.v1.html` with `window.parent` is the correct approach.

- [ ] **Step 1: Add the components import**

At the top of `ui/app.py`, add the import alongside the existing ones:

```python
import streamlit.components.v1 as components
```

The import block should now look like:

```python
import datetime
import html
import os

import requests
import streamlit as st
import streamlit.components.v1 as components
```

- [ ] **Step 2: Refactor `_render_chat()`**

Replace the entire `_render_chat()` function with:

```python
def _render_chat() -> None:
    """Render the chat panel: session history as bubbles, tool chips, and the input box."""
    if "messages" not in st.session_state:
        st.session_state.messages = []

    with st.container(height=650):
        for msg in st.session_state.messages:
            if msg["role"] == "user":
                with st.chat_message("user"):
                    st.markdown(msg["content"])
            else:
                if msg["tools_used"]:
                    chips_html = " ".join(
                        f'<span style="background:#1e3a2a;border:1px solid #2a5a3a;'
                        f'border-radius:12px;padding:3px 8px;color:#4aaa6a;'
                        f'font-size:0.75rem;">🔧 {html.escape(tool)}</span>'
                        for tool in msg["tools_used"]
                    )
                    st.markdown(
                        f'<div style="margin:4px 0 8px 0">{chips_html}</div>',
                        unsafe_allow_html=True,
                    )
                with st.chat_message("assistant"):
                    st.markdown(msg["content"])

    components.html(
        """
        <script>
        const containers = window.parent.document.querySelectorAll(
            '[data-testid="stVerticalBlockBorderWrapper"]'
        );
        if (containers.length > 0) {
            const chatBox = containers[containers.length - 1];
            chatBox.scrollTop = chatBox.scrollHeight;
        }
        </script>
        """,
        height=0,
    )

    if query := st.chat_input("Ask your coach..."):
        st.session_state.messages.append(
            {"role": "user", "content": query, "tools_used": []}
        )
        with st.spinner("Thinking..."):
            try:
                resp = requests.post(
                    f"{_API_BASE_URL}/chat",
                    json={"query": query},
                    timeout=60,
                )
                resp.raise_for_status()
                data = resp.json()
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": data["response"],
                    "tools_used": data.get("tools_used", []),
                })
            except requests.RequestException as exc:
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"Sorry, I couldn't reach the coach. Is the API running? ({exc})",
                    "tools_used": [],
                })
        st.rerun()
```

- [ ] **Step 3: Visual check — fixed window**

The Streamlit app should still be running. Hard-refresh `http://localhost:8501`.

Confirm:
- The chat panel is a fixed-height scrollable box (roughly 650 px tall)
- With no messages, it renders as an empty box
- The "Ask your coach..." input appears directly below the box, not at the page bottom
- The page itself has no vertical scrollbar

- [ ] **Step 4: Visual check — scroll behaviour**

Send several messages (the API does not need to be running — the error fallback path is fine):

1. Type a message and submit. Confirm the message appears inside the box and the input stays pinned below.
2. Send enough messages to fill the box. Confirm older messages scroll out of view upward and the latest message is visible at the bottom after each rerun.
3. Manually scroll up in the chat box. Confirm the box scrolls independently of the page.

- [ ] **Step 5: Commit**

```bash
git add ui/app.py
git commit -m "feat: fix chat to scrollable 650px window with pinned input"
```

---

## Done

After both tasks are committed, the chat window is fixed. If 650 px feels too tall or too short on the target screen, change the single integer in `st.container(height=650)` — no other code changes required.
