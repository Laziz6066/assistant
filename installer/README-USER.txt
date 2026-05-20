Voice Assistant — Portable Edition
====================================

QUICK START
  1. Распакуй эту папку куда удобно (например, C:\Apps\voice-assistant\)
  2. Запусти voice-assistant.exe
  3. В трее появится иконка. Зажми Right Ctrl и говори.

CONFIGURATION
  Отредактируй config/default.yaml в текстовом редакторе:
    tts.enabled        — озвучка ответов (требует ~63MB download первый раз)
    llm.enabled        — fallback на ollama (требует установки ollama)
    wake.enabled       — wake word "hey jarvis"
    dictation.enabled  — режим диктовки
    dialog.enabled     — multi-turn

  Команды редактируются в config/commands.yaml (формат — YAML, intent + examples).

UNINSTALL
  Просто удали эту папку. User data в %USERPROFILE%\.voice-assistant\
  (voice models, wake models) останется — удаляй вручную если нужно.

LOGS
  voice_assistant.log создаётся рядом с .exe.

ISSUES
  https://github.com/Laziz6066/assistant/issues
