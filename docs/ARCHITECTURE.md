# SYSTEM — Архитектура и руководство разработчика

Этот документ содержит внутреннее техническое описание архитектуры проекта, протоколов моста и инструкции по разработке. Краткое руководство пользователя находится в [README.md](../README.md).

---

## 1. Архитектура системы

```
obs-templates/
├── src/
│   ├── tokens/          # Дизайн-токены (цвет, типографика, геометрия system24)
│   ├── base/            # Базовые стили: fonts / reset / overlay / typography
│   ├── components/      # Визуальные модули (chat, alerts, countdown, background)
│   ├── overlays/        # Прозрачные browser sources (1920×1080) для OBS Studio
│   ├── dock/            # Встроенная OBS док-панель управления (Stream Mode)
│   ├── settings/        # Веб-панель конфигурации и аудиофайлов (Config Mode)
│   ├── sounds/          # Локальные аудиофайлы и sounds.json
│   └── fonts/           # Локальные woff2 шрифты (IBM Plex Sans, IBM Plex Mono, Space Grotesk)
├── bridge/              # Локальный асинхронный мост событий (Python, aiohttp, websockets)
│   ├── alerts_bridge.py # HTTP сервер + WebSocket broadcaster
│   ├── config.toml      # Локальная конфигурация пользователя
│   └── adapters/        # Адаптеры внешних сервисов (Twitch, Twitch Chat, DA, DonateX)
├── obs/                 # Генератор и коллекции сцен для импорта в OBS Studio
└── docs/                # Внутренняя документация проекта
```

---

## 2. Единый сервер (`alerts_bridge.py`)

Демон моста объединяет раздачу статических файлов и вещание событий в реальном времени на едином порту (`8787` по умолчанию) и работает в двух режимах:

### Режимы работы:
- **Stream Mode (по умолчанию)**: чистый сервер прямого эфира. В памяти работают только оверлеи, WebSocket-шина и док-панель. Нагрузка на память и CPU сведена к абсолютному минимуму.
- **Config Mode (`--settings`)**: режим настройки стрима до эфира. Дополнительно монтирует веб-панель `/settings` и API безопасного изменения конфигурационных файлов.

### Маршруты HTTP:
- **`/`** — автоматический редирект на пульт управления (`/dock`).
- **`/dock`** — веб-интерфейс панели управления для Custom Browser Docks в OBS.
- **`/settings`** — графическая веб-панель настроек (доступна при запуске с флагом `--settings`).
- **`/src/...`** — раздача оверлеев, стилей, компонентов, локальных шрифтов и звуков.
- **`/events`** — WebSocket-шина (`ws://127.0.0.1:8787/events`). Поддерживает многопоточную рассылку и кэширование состояний (статус сцены, активный опрос, прогноз, смайлы и бейджи) для мгновенной доставки новым оверлеям.
- **`GET /health`** — JSON-статус работы сервера, количества подключённых оверлеев, активных адаптеров и режима настроек.
- **`GET /api/config` / `POST /api/config`** — чтение и безопасное сохранение настроек в `config.toml` (с созданием `.bak` бэкапа) и `sounds.json`.
- **`POST /api/sounds/upload`** — загрузка пользовательских аудиофайлов (`.wav`, `.mp3`, `.ogg`) в `src/sounds/`.
- **`GET /api/twitch/badges`** — полный каталог 540+ официальных графических бейджей Twitch (включая все Drops).
- **`POST /api/media/skip`** — пропуск текущего трека в YouTube плеере и DonateX API.
- **`POST /api/donations/skip`** — моментальный скип доната в DonateX, DonationAlerts и гашение алерта на экране.
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
  "message": "Привет стримеру!",
  "voiceUrl": "https://cdn.donatex.gg/donation-voices/123.mp3",
  "aiVoiceUrl": "https://cdn.donatex.gg/ai/456.mp3",
  "aiResponse": "Капитан на связи! Спасибо за донат."
}
```

### Чат (`type: "chat"`):
```json
{
  "type": "chat",
  "subtype": "message | announcement | reward",
  "user": "ViewerNick",
  "text": "Hello world RainTime",
  "color": "#63E6BE",
  "announcementColor": "PRIMARY | BLUE | GREEN | ORANGE | PURPLE",
  "rewardTitle": "Попить воды",
  "rewardCost": 350,
  "badges": [
    { "set": "broadcaster", "version": "1" },
    { "set": "elden-ring-recluse", "version": "1" }
  ],
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

### Голосование / Опрос (`type: "poll"`):
```json
{
  "type": "poll",
  "action": "begin | progress | end",
  "id": "poll-uuid",
  "title": "Играем сегодня в хоррор?",
  "status": "active | completed | terminated",
  "totalVotes": 42,
  "endsAt": "2026-10-24T18:30:00Z",
  "choices": [
    { "id": "1", "title": "Да, обязательно!", "votes": 30, "percent": 71.4 },
    { "id": "2", "title": "Нет, давай чилл", "votes": 12, "percent": 28.6 }
  ]
}
```

### Прогноз / Ставки (`type: "prediction"`):
```json
{
  "type": "prediction",
  "action": "begin | progress | lock | end",
  "id": "pred-uuid",
  "title": "Выиграем следующую катку?",
  "status": "ACTIVE | LOCKED | RESOLVED",
  "totalPoints": 75300,
  "winningOutcomeId": "1",
  "outcomes": [
    { "id": "1", "title": "Победа", "color": "blue", "points": 51200, "percent": 68, "users": 70, "isWinner": true },
    { "id": "2", "title": "Поражение", "color": "pink", "points": 24100, "percent": 32, "users": 35 }
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
