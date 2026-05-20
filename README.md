# Voice PC Assistant — MVP

Push-to-talk voice assistant: hold `Right Ctrl`, speak a command, release.

## Setup
```
pip install -e ".[dev]"
python -m voice_assistant.main
```
Config: `config/default.yaml`, commands: `config/commands.yaml`.

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
