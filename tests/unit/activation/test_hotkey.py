from voice_assistant.activation.hotkey import PushToTalk


def test_press_then_release_emits_segment():
    captured = {}

    def on_capture(start_held: bool):
        captured["held"] = start_held

    ptt = PushToTalk(key_name="ctrl_r", on_state_change=on_capture)
    ptt._on_press_key()
    assert captured["held"] is True
    ptt._on_release_key()
    assert captured["held"] is False


def test_double_press_is_idempotent():
    states = []
    ptt = PushToTalk(key_name="ctrl_r", on_state_change=lambda h: states.append(h))
    ptt._on_press_key()
    ptt._on_press_key()
    assert states == [True]  # second press ignored while held
