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

## LLM Fallback (опционально)

Если правила в `config/commands.yaml` не сматчили команду — спросить локальный LLM:

1. Установи ollama: https://ollama.com/download
2. Запусти сервер: `ollama serve` (в фоне или как сервис)
3. Спулли модель: `ollama pull qwen2.5:3b-instruct` (~2 GB)
4. В `config/default.yaml` поставь `llm.enabled: true`

LLM работает локально (по умолчанию `http://localhost:11434`). Транскрипты не уходят в облако.

Если ollama не запущена или модель не скачана — ассистент работает без LLM-fallback, без ошибок.

## LLM fallback verification checklist

- [ ] `llm.enabled: false` (default): assistant starts identically to before, no ollama dependency
- [ ] `llm.enabled: true` + ollama running + model pulled: rules-known command ("открой блокнот") works as before — no LLM call (verify via DEBUG log silence)
- [ ] LLM-only command ("запусти мне телегу пожалуйста"): resolved to `open_app{app="telegram"}` (assuming alias)
- [ ] LLM-only command, ambiguous ("распакуй файлик"): `Intent.unknown()` → "Не понял, повтори"
- [ ] ollama not running while `llm.enabled: true`: first attempt → WARNING log, subsequent attempts within 60 s → no log spam, all "Не понял, повтори"
- [ ] Model not pulled: ERROR log with hint `ollama pull qwen2.5:3b-instruct`, permanent unreachable for that process
- [ ] LLM-resolved destructive intent ("выключи нахрен" → `shutdown`): triggers existing confirmation flow — destructive intents NOT bypassed

## Wake word (опционально)

Параллельно с PTT можно активировать ассистента голосом — скажи "hey jarvis",
дальше команду.

1. Включи в `config/default.yaml`: `wake.enabled: true`
2. Запусти ассистента — модель (~8 MB) скачается с openWakeWord CDN при первом старте

Все модели локальные, аудио не покидает машину.

Если `openwakeword` не установлен или модель не скачана — wake тихо отключается,
PTT продолжает работать.

Дефолтная фраза `hey jarvis`. Альтернативы (через `wake.model`):
- `alexa`
- `computer`
- `hey_mycroft`
- Свой `.onnx` (абсолютный путь)

## Wake-word verification checklist

- [ ] `wake.enabled: false` (default): assistant starts identically to before
- [ ] `wake.enabled: true`, first run: ~8 MB models download with progress log
- [ ] Second run: wake online immediately, no download
- [ ] Say "hey jarvis" then "открой блокнот" — notepad opens without PTT
- [ ] 800 ms silence after the command — ASR transcribes and dispatches
- [ ] Long command >10 s — cut off at 10 s, partial sent to ASR
- [ ] PTT still works while wake is enabled (hold Ctrl, speak)
- [ ] Background conversation (no wake) — no false triggers in 1 min
- [ ] Stop openwakeword model from disk, restart: ERROR log, PTT still works
- [ ] Ctrl+C — wake thread joins within 2 s

## System tray

Когда ассистент запущен, в системном трее появляется иконка. Правой кнопкой:
- **About** — версия ассистента (вывод в лог)
- **Quit** — корректное завершение работы (как Ctrl+C)

Отключить трей: `tray.enabled: false` в `config/default.yaml` — ассистент работает без иконки (полезно для headless/автозапуска без UI).

Если `pystray` не установлен или нет графической сессии (Linux без X/Wayland) — трей тихо отключается, ассистент работает.

## System-tray verification checklist

- [ ] Запустить — иконка появляется в трее
- [ ] Hover показывает tooltip "Voice Assistant"
- [ ] Right-click → About → версия в логе
- [ ] Right-click → Quit → ассистент корректно завершается, без traceback
- [ ] Ctrl+C тоже завершает корректно (тот же путь через `_request_shutdown`)
- [ ] `tray.enabled: false` → иконки нет, ассистент работает в консоли
- [ ] Удалить assets/tray-icon.png → запустить → fallback иконка (синий круг "VA") показывается

## Multi-turn dialog (slot inheritance)

После выполнения команды с слотом ассистент короткое время (60 с по умолчанию) помнит её аргумент и понимает местоимения:

```
открой telegram     → запускает Telegram
закрой его          → закрывает Telegram (наследуется app=telegram)
```

Работает для русских и английских местоимений: `его, её, их, это, этот, эту, того, тому, ту, it, this, that`. Состояние очищается через `dialog.context_ttl_s` секунд.

Отключить: `dialog.enabled: false` в `config/default.yaml`. Контекст хранится только в памяти — после рестарта пустой.

## Multi-turn dialog verification checklist

- [ ] "открой блокнот" → "закрой его" → блокнот закрывается
- [ ] Пауза 70 секунд между turns → второй turn даёт "Не понял, повтори"
- [ ] "сверни всё" (slotless) → "закрой его" → "Не понял" (нет entity)
- [ ] `dialog.enabled: false` → "открой блокнот" → "закрой его" → "Не понял"
- [ ] "открой telegram" → "открой это" → пытается открыть telegram повторно
- [ ] Цепочка: `open_app(telegram)` → `open_app(chrome)` → "закрой его" → закрывает Chrome (последняя entity)
- [ ] `confirm_yes` после команды НЕ затирает context: "выключи компьютер" → "да" → "верни его" не наследует "yes"

## Dictation mode (надиктовка)

Скажи "режим диктовки" / "начни диктовать" / "диктуй" — ассистент перейдёт в режим диктовки. Дальше всё, что ты говоришь, печатается в активное окно (документ, email, чат). Знаки препинания произноси словами: `точка, запятая, вопрос, восклицательный, двоеточие, тире, дефис, точка с запятой, новая строка`.

Чтобы выйти: "стоп диктовка" / "конец диктовки" / "выход из диктовки".

Печатается в активный фокус. Если в момент диктовки открыт UAC-диалог, secure desktop или окно без текстового поля — нажатия теряются. Перед началом убедись, что фокус в нужном текстовом поле.

Пример:
```
ты: режим диктовки
ассистент: Режим диктовки

ты:  привет мама точка как у тебя дела вопрос
напечатано: привет мама. как у тебя дела?

ты: стоп диктовка
ассистент: Готово
```

Отключить весь режим: `dictation.enabled: false` в `config/default.yaml` (фраза "режим диктовки" будет давать "Режим диктовки выключен").

## Dictation verification checklist

- [ ] "режим диктовки" → TTS подтверждает + переход в dictation
- [ ] "привет всем точка" → "привет всем." напечатано в активном Notepad
- [ ] "новая строка" → перевод строки
- [ ] "сколько времени вопрос" → "сколько времени?"
- [ ] "молоко запятая хлеб запятая сахар" → "молоко, хлеб, сахар"
- [ ] "стоп диктовка" → выход, обычные команды снова работают
- [ ] Длинная фраза 50+ слов печатается полностью
- [ ] `dictation.enabled: false` → "режим диктовки" не активирует mode (TTS говорит "Режим диктовки выключен")
- [ ] Multi-turn context НЕ обновляется во время диктовки (после "стоп" "закрой его" даёт "Не понял")

## Build (для разработчика)

Производит portable .zip с .exe и user-editable configs:

```
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
installer\build.bat
```

Результат: `dist/voice-assistant-0.1.0.zip` (~265 MB).

Сборка занимает 3-5 минут. Если падает на missing hidden import — добавь его в `hiddenimports` в `installer/voice_assistant.spec` и пересобери.

## Install (для конечного пользователя)

1. Скачай `voice-assistant-0.1.0.zip` с релизной страницы
2. Распакуй в удобную папку (например, `C:\Apps\voice-assistant\`)
3. Запусти `voice-assistant.exe`
4. Опционально отредактируй `config/default.yaml` чтобы включить TTS / wake / LLM / dictation

User data (voice models, wake models) хранится в `%USERPROFILE%\.voice-assistant\`. Удаление папки приложения её не очищает — удали вручную если нужен полный clean.

## Installer verification checklist

- [ ] `installer\build.bat` завершается без ошибок (~3-5 минут)
- [ ] `dist/voice-assistant-0.1.0.zip` создан, размер ~265 MB
- [ ] Распаковка в чистую папку (без виртуального окружения рядом)
- [ ] Двойной клик по `voice-assistant.exe` — окно консоли + иконка в трее
- [ ] PTT: Right Ctrl → "открой блокнот" → notepad запускается
- [ ] `voice_assistant.log` создаётся рядом с .exe
- [ ] Включить `tts.enabled: true` в `config/default.yaml` → перезапустить → голос качается в `%USERPROFILE%\.voice-assistant\voices\`
- [ ] Tray → Quit → процесс корректно завершается, лог-файл не залочен
- [ ] Удалить папку → нет следов в Program Files / реестре
- [ ] (Опционально) Защитник Windows не флагует .exe как malware
