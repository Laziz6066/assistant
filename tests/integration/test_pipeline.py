import numpy as np
from unittest.mock import MagicMock
from voice_assistant.config import AppConfig
from voice_assistant.nlu.rules import RulesRouter
from voice_assistant.executor.registry import Registry
from voice_assistant.executor.context import ExecutorContext
from voice_assistant.core.types import AudioSegment, Transcript
from voice_assistant.main import Pipeline
import voice_assistant.executor.plugins.apps as apps


def test_open_app_flows_from_transcript_to_plugin(tmp_path):
    cmds = tmp_path / "commands.yaml"
    cmds.write_text(
        '- intent: open_app\n'
        '  examples: ["открой {app}"]\n'
        '  slots: {app: string}\n', encoding="utf-8")

    cfg = AppConfig(app_aliases={"телега": "telegram"})
    asr = MagicMock()
    asr.transcribe.return_value = Transcript("открой телега", "ru", 0.9, 500)
    nlu = RulesRouter(commands_path=cmds, fuzzy_threshold=85)
    reg = Registry()
    apps.register(reg)
    ops = MagicMock()
    ctx = ExecutorContext(config=cfg, platform_ops=ops)
    feedback = MagicMock()

    pipe = Pipeline(cfg, asr, nlu, reg, ctx, feedback)
    pipe.process_segment(AudioSegment(np.zeros(8000, dtype=np.int16), 16000))

    ops.launch_app.assert_called_once_with("telegram")
    feedback.emit.assert_called_once()
    assert feedback.emit.call_args.kwargs.get("success", True) is True
