# Voice PC Assistant — MVP

Push-to-talk voice assistant: hold `Right Ctrl`, speak a command, release.

## Setup
```
pip install -e ".[dev]"
python -m voice_assistant.main
```
Config: `config/default.yaml`, commands: `config/commands.yaml`.

## Privacy
- `store_transcripts: false` in `config/default.yaml` (default) keeps ASR text out of the log; only confidence scores are recorded.
- Known limitation: clipboard content read by `прочитай буфер` is echoed in feedback output (stdout + notification) and logged via `CLIFeedback`. Remove the `clipboard_read` rule from `config/commands.yaml` if this is unacceptable.

## Manual verification checklist (run before tagging MVP)
- [ ] Hold Right Ctrl, say "открой блокнот" → notepad launches
- [ ] "сверни всё" → desktop shows
- [ ] "закрой текущее окно" → active window closes
- [ ] "найди в гугле погода" → browser opens Google results
- [ ] "открой папку загрузки" → Downloads opens
- [ ] "скопируй" then "вставь" → clipboard works
- [ ] "громкость 20" → system volume changes
- [ ] "заблокируй экран" → screen locks
- [ ] "выключи компьютер" → asks confirmation; "да" within 5s proceeds (cancel by waiting out timeout during test)
- [ ] Garbage speech → "Не понял, повтори", no action
- [ ] Ctrl+C → clean shutdown, no traceback
- [ ] Latency end-of-speech → action start ≤ 1.5s (use benchmark_asr.py)

## TTS (text-to-speech)

The assistant speaks responses via Piper. On first run the default voice
(`ru_RU-irina-medium`, ~63 MB) downloads to `~/.voice-assistant/voices/`.

Disable TTS in `config/default.yaml`:
```
tts:
  enabled: false
```

## Privacy

- Audio capture stays on-device. ASR runs locally via faster-whisper.
- Set `store_transcripts: false` (default) so transcript text is not logged.
- TTS feedback is logged via `CLIFeedback`; the clipboard plugin's
  `прочитай буфер` echoes clipboard contents into feedback (and logs).
  Disable that intent in `config/commands.yaml` if you don't want it.

## TTS verification checklist

- [ ] First run: voice model downloads (~30 s) with progress log every 10 MB
- [ ] Second run: TTS available immediately (no download)
- [ ] "открой блокнот" → notepad launches AND voice says "Открыл блокнот"
- [ ] Long response → press PTT mid-playback → audio cuts off cleanly
- [ ] Ctrl+C during TTS playback → shuts down within 2 s
- [ ] Disconnect network, delete voice from `~/.voice-assistant/voices/` → assistant starts text-only with ERROR log
- [ ] Set `tts.enabled: false` → no Piper import, normal text-only operation
