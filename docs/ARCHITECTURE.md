# SYSTEM — Архитектура и руководство разработчика

Этот документ содержит внутреннее техническое описание архитектуры проекта, протоколов моста и инструкции по разработке. Краткое руководство пользователя находится в [README.md](../README.md).

---

## 1. Архитектура системы

```
obs-templates/
├── src/
│   ├── tokens/          # Дизайн-токены (цвет, типографика, геометрия system24)
│   ├── base/            # Базовые стили: fonts / reset / overlay / typography
│   ├── components/      # Визуальные модули (chat, alerts, countdown и др.)
│   ├── overlays/        # Прозрачные browser sources (1920×1080) для OBS
│   ├── scenes/          # Чертежи композиций сцен
│   ├── dock/            # Встроенная OBS док-панель управления
│   ├── preview/         # Тест-стенд компонентов в живом loop
│   ├── sounds/          # Локальные аудиофайлы и sounds.json
│   └── fonts/           # Локальные woff2 шрифты (IBM Plex Mono, Space Grotesk)
├── bridge/              # Локальный асинхронный мост событий (Python, aiohttp)
│   ├── alerts_bridge.py # HTTP сервер + WebSocket broadcaster
│   └── adapters/        # Адаптеры внешних сервисов (Twitch, Chat, DA, DonateX)
├── obs/                 # Официальные коллекции сцен для импорта в OBS Studio
└── docs/                # Внутренняя документация проекта
```

---

## 2. Единый сервер (`alerts_bridge.py`)

Демон моста объединяет раздачу статических файлов и вещание событий в реальном времени на едином порту (`8787` по умолчанию):

- **`/`** — автоматический редирект на тестовый стенд (`/src/preview/index.html`).
- **`/dock`** — веб-интерфейс панели управления для Custom Browser Docks в OBS.
- **`/src/...`** — раздача оверлеев, стилей, компонентов и медиа.
- **`/events`** — WebSocket-шина (`ws://127.0.0.1:8787/events`). Поддерживает многопоточную рассылку подключённым оверлеям.
- **`POST /notify`** — HTTP API для эмуляции или внешней отправки событий:
  ```bash
  # Пример отправки алерта:
  curl -X POST http://127.0.0.1:8787/notify \
    -H 'Content-Type: application/json' \
    -d '{"kind": "donate", "user": "Alex", "amount": "$25.00", "message": "Good stream!"}'

  # Пример отправки сообщения в чат:
  curl -X POST http://127.0.0.1:8787/notify \
    -H 'Content-Type: application/json' \
    -d '{"type": "chat", "user": "Tester", "text": "RainTime hello chat"}'

  # Пример смены состояния сцены:
  curl -X POST http://127.0.0.1:8787/notify \
    -H 'Content-Type: application/json' \
    -d '{"type": "status", "state": "brb"}'
  ```
- **`GET /health`** — JSON-статус работы сервера, количества подключённых оверлеев и адаптеров.

---

## 3. Модели событий WebSocket

Все сообщения передаются в формате JSON:

### Алерт (`type: "alert"`):
```json
{
  "type": "alert",
  "kind": "donate | sub | resub | gift | raid | cheer | follow",
  "title": "DONATION",
  "body": "username · $25.00",
  "user": "username",
  "amount": "$25.00",
  "message": "Привет стримеру!"
}
```

### Чат (`type: "chat"`):
```json
{
  "type": "chat",
  "user": "ViewerNick",
  "text": "Hello world RainTime",
  "color": "#63E6BE",
  "emotes": [
    {
      "id": "25",
      "start": 0,
      "end": 5,
      "url": "https://static-cdn.jtvnw.net/emoticons/v2/25/default/dark/2.0"
    }
  ]
}
```

### Состояние сцены (`type: "status"`):
```json
{
  "type": "status",
  "state": "starting | main | chatting | focus | brb | ending"
}
```

### Управление таймером (`type: "countdown_control"`):
```json
{
  "type": "countdown_control",
  "action": "set | adjust | pause | resume | toggle_pause | reset",
  "minutes": 10,
  "deltaSeconds": 60
}
```

---

## 4. Автозапуск через Systemd (Linux)

Для постоянной фоновой работы без открытия терминала:

Создай файл `~/.config/systemd/user/system-bridge.service`:
```ini
[Unit]
Description=SYSTEM alerts & overlay bridge
After=network.target

[Service]
WorkingDirectory=%h/OBS-Templates/bridge
ExecStart=%h/OBS-Templates/bridge/.venv/bin/python alerts_bridge.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
```

Команды управления:
```bash
systemctl --user daemon-reload
systemctl --user enable --now system-bridge.service
systemctl --user status system-bridge.service
```

---

## 5. Руководство для разработчиков компонентов

- **Стилизация**: CSS-файл размещается рядом с компонентом в `src/components/`, имена классов имеют префикс компонента (`.chat__*`, `.alert__*`), геометрия строится строго по токенам из `src/tokens/tokens.css` (радиус 0px, 1px границы).
- **Изоляция скриптов**: все JS-скрипты оверлеев и компонентов оборачиваются в IIFE (`(() => { ... })()`), чтобы предотвратить конфликт глобальных переменных при подключении в общие страницы.
- **Адаптеры**: новый адаптер создаётся в `bridge/adapters/<name>.py` с асинхронной функцией `run(config, broadcast)` и регистрируется в словаре `spawn_adapters` файла `alerts_bridge.py`.
