# IN ALPHA: FOR PREVIEW ONLY. WAIT UNTIL PUBLIC RELEASE
---

# SYSTEM — OBS Broadcast Templates

TUI-inspired визуальная система для стрима в стилистике **system24**: эфир как строгий интерфейс технической системы с состояниями (`starting` → `main` → `chatting` → `focus` → `brb` → `ending`).

Тёмный монохромный UI, моноширинная типографика, живой чат со смайлами 7TV и медиаконтентом, вспышки донатов с сообщениями зрителей, таймер с управлением из OBS и модульные звуковые эффекты. Всё работает локально, без сторонних платных сервисов.

---

## Возможности

- **6 готовых сцен**: Starting Soon, Main (Gameplay), Chatting, Focus, Break (BRB), Ending.
- **Импорт в OBS за 1 клик**: готовый файл коллекции сцен `obs/SYSTEM_Scene_Collection.json`.
- **Встроенная панель управления (OBS Dock)**: переключение состояний, тест алертов, управление таймером и очистка чата прямо из интерфейса OBS.
- **Twitch-чат без токенов**: официальный анонимный Twitch IRC WebSocket, поддержка встроенных смайлов Twitch, глобальных и канальных смайлов 7TV, а также встроенное отображение картинок и гифок (JeetBot, Tenor, Giphy, Imgur).
- **Вспышки донатов**: классические flash-алерты с отображением суммы, ника и текста сообщения зрителя.
- **Кастомные звуки**: модульная папка `src/sounds/` с поддержкой любых `.wav` / `.mp3` и раздельной настройкой громкости под каждое событие.
- **Динамический таймер**: обратный отсчёт с установкой минут, паузой и сбросом в реальном времени из дока.
- **Локальный единый мост**: один процесс раздаёт статику, события WebSocket и API на порту `8787`.

---

## Быстрый старт

### 1. Клонирование и запуск

```bash
git clone https://github.com/Vokiry/OBS-Templates.git
cd OBS-Templates
./start.sh
```

Скрипт автоматически подготовит окружение Python, создаст файл конфигурации и запустит единый сервер.

- **Панель управления (OBS Dock)**: http://localhost:8787/dock
- **Тестовый стенд (Live loop)**: http://localhost:8787/src/preview/
- **Чертежи сцен**: http://localhost:8787/src/scenes/main.html

---

### 2. Подключение в OBS Studio

#### Импорт коллекции сцен (Рекомендуется)
1. В OBS Studio: **Коллекция сцен (Scene Collection) → Импорт (Import)**.
2. Выбери файл `obs/SYSTEM_Scene_Collection.json`.
3. В меню коллекций выбери **SYSTEM Broadcast Templates**.
4. Все 6 сцен созданы, источники 1920×1080 выставлены по слоям, прозрачность и звук включены. Остаётся лишь назначить захват экрана/игры и веб-камеру.

#### Добавление пульта управления (Custom Browser Dock)
1. В OBS: **Док-панели (Docks) → Пользовательские док-панели браузера (Custom Browser Docks)**.
2. Название: `SYSTEM Dock`, URL: `http://localhost:8787/dock`.
3. Нажми «Применить» — панель управления закрепится в интерфейсе OBS.

---

## Настройка интеграций (`bridge/config.toml`)

Файл `bridge/config.toml` создаётся автоматически при первом запуске:

```toml
[server]
host = "127.0.0.1"
port = 8787

# Чат Twitch (работает сразу, токены НЕ нужны)
[twitch_chat]
enabled = true
channel = "твой_ник_на_твиче"

# События Twitch: сабы, рейды, битсы (требует Client ID / Secret)
[twitch]
enabled = false
client_id = ""
client_secret = ""
include_follows = false

# Донаты DonationAlerts
[donationalerts]
enabled = false
access_token = ""
```

---

## Документация для разработчиков

Подробные исследования, архитектурные спецификации и руководство разработчика вынесены в папку [`docs/`](docs/):

- [`docs/DESIGN.md`](docs/DESIGN.md) — философия дизайна, токены (system24 unrounding, палитра, типографика).
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — техническая архитектура сервера, схемы событий WebSocket, запуск через systemd.
- [`docs/RESEARCH.md`](docs/RESEARCH.md) — исследование протоколов (Twitch IRC/EventSub, Centrifugo, CEF Browser Source).
- [`docs/PLAN.md`](docs/PLAN.md) — план разработки и бэклог.

---

## Лицензия

Проект распространяется по лицензии **[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)** (Attribution–NonCommercial–ShareAlike).
Полный текст — в файле [`LICENSE`](LICENSE).
