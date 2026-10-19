"""Canvas scenes shared by the canvas tests (ADR-2249 D1, PLAN-0947 P2)."""

CLEAN = {
    "eyebrow": "Caching", "title": "Why a cache speeds up the second request", "sketch": True,
    "elements": [
        {"type": "person", "id": "user", "text": "User", "at": {"col": 0, "row": 2, "w": 2, "h": 2}, "step": 1},
        {"type": "round", "id": "app", "text": "App server", "at": {"col": 3, "row": 2, "w": 2, "h": 2}, "step": 2},
        {"type": "arrow", "from": "user", "to": "app", "step": 2},
        {"type": "cylinder", "id": "cache", "text": "Cache", "at": {"col": 6, "row": 0, "w": 2, "h": 2}, "step": 3},
        {"type": "arrow", "from": "app", "to": "cache", "step": 3},
        {"type": "cylinder", "id": "db", "text": "Database", "at": {"col": 9, "row": 2, "w": 3, "h": 2}, "step": 4},
        {"type": "arrow", "from": "app", "to": "db", "text": "miss", "step": 4},
        {"type": "label", "id": "note", "text": "A hit skips the database", "at": {"col": 3, "row": 5, "w": 6, "h": 1},
         "style": "note", "font": "s", "step": 5},
        {"type": "underline", "target": "note", "tone": "success", "step": 5},
    ],
}

# Passes validation (distinct cells, text fits) but is wrong once drawn: the arrow from a to c runs
# straight through b (stroke-shape), and the arrow label sits on top of b (text-shape).
THROUGH_A_BOX = {
    "title": "An arrow through a box",
    "elements": [
        {"type": "box", "id": "a", "text": "Alpha", "at": {"col": 0, "row": 2, "w": 2, "h": 2}, "step": 1},
        {"type": "box", "id": "b", "text": "Bravo", "at": {"col": 5, "row": 2, "w": 2, "h": 2}, "step": 1},
        {"type": "box", "id": "c", "text": "Charlie", "at": {"col": 10, "row": 2, "w": 2, "h": 2}, "step": 1},
        {"type": "arrow", "from": "a", "to": "c", "text": "passes through", "step": 2},
    ],
}
