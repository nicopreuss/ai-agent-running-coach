# Chat Fixed Window — Design Spec

**Date:** 2026-05-04
**Status:** Approved

## Problem

The chat panel in `ui/app.py` renders messages by looping over `st.session_state.messages` with
`st.chat_message`. As the conversation grows, the right column grows with it, pushing the page
down. The dashboard becomes unreachable without scrolling, and the input box drifts out of view.

## Goal

Fix the chat to a scrollable window of a set height. The page itself should not scroll. The input
box must always be visible at the bottom of the chat panel.

## Design decisions

- **Both panels fill the viewport (conceptually):** the layout goal is that no content pushes the
  page beyond the visible screen area.
- **Title bar stays:** `st.title("Running Coach")` remains at the top. Panel headers
  (`st.subheader`) remain as-is.
- **Implementation: `st.container(height=650)`** — native Streamlit, no fragile CSS selectors.
  The message history renders inside the container; `st.chat_input` sits outside it, pinned below.

## Changes

### `ui/app.py` only — no other files touched

**1. CSS injection (added once, near top of layout section):**

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

- `padding-bottom: 0rem` prevents Streamlit adding blank space below the columns.
- `overflow: hidden` on `section.main` prevents the outer page from showing a scrollbar.

**2. `_render_chat()` refactor:**

```python
def _render_chat() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []

    with st.container(height=650):          # fixed scrollable window
        for msg in st.session_state.messages:
            ...                             # existing render logic, unchanged

    if query := st.chat_input("Ask your coach..."):
        ...                                 # existing send logic, unchanged
```

- The `for` loop moves inside `st.container(height=650)`.
- After the container, a one-line `st.markdown` injects a `<script>` tag that scrolls the
  container to the bottom — Streamlit does not do this automatically on rerun.
- `st.chat_input` stays outside the container — Streamlit renders it as a sticky bottom input.
- The spinner and `st.rerun()` calls are untouched.

## What does not change

- Column ratio `[3, 2]` (dashboard 60%, chat 40%)
- Sidebar ("Refresh All" button)
- API call logic, error handling, tool chips
- Any file outside `ui/app.py`

## Height choice

`650` is the starting value. It is a plain integer in the function — easy to adjust if it looks
too tall or short on the target screen.
