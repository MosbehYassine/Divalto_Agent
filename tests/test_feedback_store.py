import json
import tempfile
from pathlib import Path

import feedback_store


def test_append_answer_feedback_writes_jsonl(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "feedback.jsonl"
        monkeypatch.setattr(feedback_store, "feedback_file_path", lambda: path)

        out = feedback_store.append_answer_feedback(
            rating="up",
            user_query="Combien de clients ?",
            assistant_answer="Il y a 80 clients.",
            mode="classic",
            message_id="msg-1",
        )

        assert out["ok"] is True
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        row = json.loads(lines[0])
        assert row["rating"] == "up"
        assert row["user_query"] == "Combien de clients ?"
        assert row["assistant_answer"] == "Il y a 80 clients."
