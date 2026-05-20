"""End-to-end multi-turn dialog test.

Uses real RulesRouter, ContextStore, ContextualRouter; mocks ASR and
platform_ops. Verifies that 'закрой его' after 'открой телега' is
resolved to close_app{app=telegram} via the app_aliases mapping.
"""
import numpy as np
from unittest.mock import MagicMock

from voice_assistant.config import AppConfig
from voice_assistant.nlu.rules import RulesRouter
from voice_assistant.nlu.context_store import ContextStore
from voice_assistant.nlu.contextual import ContextualRouter
from voice_assistant.executor.registry import Registry
from voice_assistant.executor.context import ExecutorContext
from voice_assistant.executor.plugins import apps as apps_plugin
from voice_assistant.core.types import AudioSegment, Transcript
from voice_assistant.main import Pipeline


def test_two_turn_open_then_close(tmp_path):
    cmds = tmp_path / "commands.yaml"
    cmds.write_text(
        '- intent: open_app\n'
        '  examples: ["открой {app}", "запусти {app}"]\n'
        '  slots: {app: string}\n'
        '- intent: close_app\n'
        '  examples: ["закрой {app}"]\n'
        '  slots: {app: string}\n',
        encoding="utf-8")

    cfg = AppConfig(app_aliases={"телега": "telegram"})
    asr = MagicMock()
    store = ContextStore(max_size=5, ttl_s=60.0)
    inner_nlu = RulesRouter(commands_path=cmds, fuzzy_threshold=85)
    nlu = ContextualRouter(inner=inner_nlu, store=store)
    reg = Registry()
    apps_plugin.register(reg)
    ops = MagicMock()
    ctx = ExecutorContext(config=cfg, platform_ops=ops)
    feedback = MagicMock()

    pipe = Pipeline(cfg, asr, nlu, reg, ctx, feedback,
                     context_store=store)

    # Turn 1: "открой телега" — opens telegram, store records intent
    asr.transcribe.return_value = Transcript("открой телега", "ru", 0.9, 500)
    pipe.process_segment(AudioSegment(np.zeros(8000, dtype=np.int16), 16000))
    ops.launch_app.assert_called_once_with("telegram")

    # Turn 2: "закрой его" — should resolve to close_app(app=telegram)
    asr.transcribe.return_value = Transcript("закрой его", "ru", 0.9, 500)
    pipe.process_segment(AudioSegment(np.zeros(8000, dtype=np.int16), 16000))

    # close_app via apps_plugin → platform_ops.close_app("telegram")
    ops.close_app.assert_called_once_with("telegram")
