"""End-to-end dictation test.

Real RulesRouter + ModeStore + DictationProcessor + plugins; mocks ASR
and platform_ops. Verifies the 3-turn flow:
  1. "режим диктовки"      → mode flips to dictation
  2. "привет мама точка"   → ops.type_text("привет мама.")
  3. "стоп диктовка"        → mode flips back to command
"""
import numpy as np
from unittest.mock import MagicMock

from voice_assistant.config import AppConfig
from voice_assistant.nlu.rules import RulesRouter
from voice_assistant.executor.registry import Registry
from voice_assistant.executor.context import ExecutorContext
from voice_assistant.executor.plugins import dictation as dictation_plugin
from voice_assistant.dictation.mode_store import ModeStore
from voice_assistant.dictation.processor import DictationProcessor
from voice_assistant.core.types import AudioSegment, Transcript
from voice_assistant.main import Pipeline


def test_three_turn_dictation_flow(tmp_path):
    cmds = tmp_path / "commands.yaml"
    cmds.write_text(
        '- intent: start_dictation\n'
        '  examples: ["режим диктовки", "диктуй"]\n'
        '  slots: {}\n'
        '- intent: stop_dictation\n'
        '  examples: ["стоп диктовка", "конец диктовки"]\n'
        '  slots: {}\n',
        encoding="utf-8")

    cfg = AppConfig()
    asr = MagicMock()
    nlu = RulesRouter(commands_path=cmds, fuzzy_threshold=85)
    reg = Registry()
    dictation_plugin.register(reg)
    ops = MagicMock()
    store = ModeStore()
    proc = DictationProcessor(platform_ops=ops)
    ctx = ExecutorContext(config=cfg, platform_ops=ops, mode_store=store)
    feedback = MagicMock()

    pipe = Pipeline(cfg, asr, nlu, reg, ctx, feedback,
                     mode_store=store, dictation_processor=proc)

    # Turn 1: enter dictation
    asr.transcribe.return_value = Transcript("режим диктовки", "ru", 0.95, 500)
    pipe.process_segment(AudioSegment(np.zeros(8000, dtype=np.int16), 16000))
    assert store.is_dictation() is True
    ops.type_text.assert_not_called()  # not yet — we just toggled mode

    # Turn 2: dictate
    asr.transcribe.return_value = Transcript(
        "привет мама точка", "ru", 0.95, 500)
    pipe.process_segment(AudioSegment(np.zeros(8000, dtype=np.int16), 16000))
    ops.type_text.assert_called_once_with("привет мама.")

    # Turn 3: exit dictation
    asr.transcribe.return_value = Transcript("стоп диктовка", "ru", 0.95, 500)
    pipe.process_segment(AudioSegment(np.zeros(8000, dtype=np.int16), 16000))
    assert store.is_command() is True
