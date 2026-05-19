from voice_assistant.core.queues import PipelineQueues, STOP


def test_queues_exist_and_stop_is_singleton():
    q = PipelineQueues()
    assert q.speech_q is not None
    assert q.asr_q is not None
    assert q.nlu_q is not None
    assert q.exec_q is not None
    q.speech_q.put(STOP)
    assert q.speech_q.get() is STOP
