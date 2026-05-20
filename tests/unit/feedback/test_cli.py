from unittest.mock import patch
from voice_assistant.feedback.cli import CLIFeedback


def test_emit_prints_and_notifies(capsys):
    fb = CLIFeedback()
    with patch.object(fb, "_notify") as notify:
        fb.emit("Открыл telegram", success=True)
    out = capsys.readouterr().out
    assert "Открыл telegram" in out
    assert "[OK]" in out
    notify.assert_called_once()


def test_emit_failure_marked(capsys):
    fb = CLIFeedback()
    with patch.object(fb, "_notify"):
        fb.emit("Не понял", success=False)
    out = capsys.readouterr().out
    assert "Не понял" in out
    assert "[!!]" in out
