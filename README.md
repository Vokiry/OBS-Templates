# IN ALPHA: FOR PREVIEW ONLY. WAIT UNTIL PUBLIC RELEASE
---
# SYSTEM — OBS broadcast templates

TUI-inspired визуальная система для стрима: эфир как интерфейс технической
системы, который меняет состояние (starting → main → chatting → brb → ending).
Спокойный тёмный UI, моноширинная типографика, живые алерты и музыкальный
плеер. Работает локально, без внешних сервисов.

Это руководство — путь от клонирования репозитория до полностью собранного
эфира в OBS. Внутренние документы (дизайн-концепция, исследования, план
разработки) лежат в [`docs/`](docs/).

## Возможности

- 6 готовых сцен: starting, main, chatting, focus, break, ending
- Прозрачные оверлеи-компоненты с позиционированием через URL (`?pos=`)
- Движок алертов: FIFO-очередь, ASCII-анимация (spinner, печать заголовка,
  прогресс-бар), авто-скрытие
- Мост событий: Twitch (subs/raids/cheers) + DonationAlerts — локальный демон,
  без публичного URL и чужих виджетов
- Обратный отсчёт, live feed, чат-панель, индикатор состояния эфира

## Требования

- OBS Studio 28+ (Browser Source)
- Python 3.11+ — только для моста событий и локального превью-сервера
- Интернет — только один раз, для OAuth-токенов Twitch/DonationAlerts

## Быстрый старт (1 команда)

```bash
git clone https://github.com/Vokiry/OBS-Templates.git
cd OBS-Templates
./start.sh
```

Скрипт автоматически подготовит окружение, запустит единый сервер на порту `8787` и зарегистрирует сцены в OBS.

- **Панель управления (OBS Dock)**: http://localhost:8787/dock
- **Тест-стенд компонентов (живой loop)**: http://localhost:8787/src/preview/
- **Сцены**: http://localhost:8787/src/scenes/main.html (навигация в шапке)
- **Готовая коллекция сцен для OBS**: `obs/SYSTEM_Scene_Collection.json` (импортируется в 1 клик!)

## Структура проекта

```
obs-templates/
├── src/
│   ├── tokens/          # design tokens (цвет, типографика, геометрия, motion)
│   ├── base/            # базовые стили: fonts / reset / overlay / typography
│   ├── components/      # переиспользуемые компоненты (css + js)
│   ├── overlays/        # прозрачные browser source для OBS
│   ├── scenes/          # превью-чертежи сцен 1920×1080
│   ├── preview/         # тест-стенд
│   └── fonts/           # локальные woff2
├── bridge/              # мост событий (python)
└── docs/                # внутренняя документация
```

## Сцены

`src/scenes/*.html` — чертежи полной композиции. Захват игры/камеры показан
плейсхолдерами; в OBS они заменяются реальными источниками.

| Файл | Композиция |
|---|---|
| `starting.html` | развёрнутый плеер с лирикой слева, компактный countdown справа-сверху, справа колонка chat + live feed |
| `main.html` | игра на весь экран, справа колонка: плеер + live feed, чат, камера снизу |
| `chatting.html` | камера (vtube) на весь экран без фона, слева плеер+фид, справа чат |
| `focus.html` | игра почти на весь экран, маленькая камера, минимум UI |
| `break.html` | PAUSED / BRB в центре с компактным плеером, по сторонам чат и live feed |
| `ending.html` | итоговая карточка, next stream, ссылки, SYSTEM OFFLINE |

## Оверлеи для OBS

Каждый файл из `src/overlays/` — самостоятельный прозрачный browser source
1920×1080. Компонент позиционируется параметром `?pos=`, а не перемещением
источника.

| Файл | Параметры | Описание |
|---|---|---|
| `background.html` | — | фон + HUD-уголки (нижний слой) |
| `scene-indicator.html` | `?state=` | индикатор состояния: `offline`, `starting`, `intro`, `main`, `chatting`, `focus`, `brb`, `ending` |
| `now-playing.html` | `?variant=compact\|expanded` | виджет трека; expanded центрируется сам |
| `activity-feed.html` | `?ws=` | лента донатов/сабов/рейдов; авто-подключение к мосту |
| `chat.html` | `?demo=loop`, `?max=20`, `?ws=` | стилизованный чат; авто-подключение к мосту |
| `countdown.html` | `?minutes=10` | обратный отсчёт |
| `activity-pulse.html` | — | пульс активности |
| `ending-card.html` | `?message=`, `?next=`, `?twitch=`, `?discord=` | итоговая карточка завершения стрима |
| `alerts.html` | `?demo=once\|loop`, `?hold=`, `?max=`, `?sfx=off`, `?ws=` | движок алертов с ретро-бипами; авто-подключение к мосту (`ws://127.0.0.1:8787/events`) |

Позиционирование (для всех, кроме `background.html`):

```
?pos=top-left | top-center | top-right | center-left | center | center-right | bottom-left | bottom-center | bottom-right
```

Примеры:

```
src/overlays/now-playing.html?variant=compact&pos=bottom-left
src/overlays/scene-indicator.html?state=brb&pos=top-left
src/overlays/countdown.html?minutes=15&pos=center
```

## Настройка в OBS

### Вариант 1: Импорт за 1 клик (Рекомендуется)

1. Запусти `./start.sh`.
2. В OBS Studio: **Коллекция сцен (Scene Collection) → Импорт (Import)** → выбери файл `obs/SYSTEM_Scene_Collection.json`.
3. В списке коллекций сцен переключись на **SYSTEM Broadcast Templates**.
4. Все 6 сцен созданы, источники 1920×1080 расставлены по слоям, прозрачность и звуки включены!

### Панель управления в OBS (Custom Browser Dock)

1. В OBS Studio: **Док-панели (Docks) → Пользовательские док-панели браузера (Custom Browser Docks)**.
2. Имя: `SYSTEM Dock`, URL: `http://localhost:8787/dock`.
3. Нажми «Применить» — панель управления появится прямо в интерфейсе OBS!
   - 1 клик для проверки алертов (саб, донат, рейд);
   - переключение статусов сцен;
   - проверка чата и телеметрии.

### Вариант 2: Ручное добавление оверлеев

1. **Sources → + → Browser**:
   - URL источника: `http://localhost:8787/src/overlays/<компонент>.html?pos=...` (или локальный файл через галочку Local file).
2. **Ширина/высота: 1920 × 1080.** Не оставляй 800×600.
3. Порядок слоёв снизу вверх:
   `background → game capture / vtube → camera → chat → activity-feed → now-playing → scene-indicator → activity-pulse → alerts`

### Сборка сцен

| Сцена OBS | Источники |
|---|---|
| Starting soon / Intro | background, now-playing(`?variant=expanded&pos=center-left`), countdown(`?minutes=`), chat, activity-feed, scene-indicator(`?state=starting` или `intro`), pulse |
| Main | game capture (весь экран), chat, activity-feed, now-playing(compact), camera, scene-indicator(`?state=main`), pulse |
| Chatting | background, vtube-модель (весь экран), chat, activity-feed, now-playing(compact), scene-indicator(`?state=chatting`), pulse |
| Focus | game capture, маленькая камера, scene-indicator(`?state=focus`) |
| Break | background, chat, activity-feed, now-playing(compact, центр), scene-indicator(`?state=brb`), pulse |
| Ending | background, ending-card, scene-indicator(`?state=ending`) |

## Мост событий (bridge)

Локальный демон `bridge/`: собирает события Twitch и DonationAlerts,
нормализует и раздаёт их в оверлеи алертов, фида и чата по WebSocket
(`ws://127.0.0.1:8787/events`). Без публичного URL, без чужих виджетов.

| Адаптер | Источник | События | Статус |
|---|---|---|---|
| twitch | Twitch EventSub WebSocket | sub / resub / gift / cheer / raid (+follow опционально) | готов |
| twitch_chat | Twitch IRC WebSocket | chat (анонимное чтение, без OAuth) | готов |
| donationalerts | Centrifugo WS, канал `$alerts:donation` | donate | готов |
| donatex | SignalR + API-ключ | donate | в разработке |

### Установка

```bash
cd bridge
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp config.example.toml config.toml
```

### Настройка Twitch

1. Зарегистрируй приложение на https://dev.twitch.tv/console/apps/create:
   - OAuth redirect URLs: `http://localhost:3000` (twitchAPI использует его);
   - Category: Chat Bot.
2. Скопируй **Client ID** и создай **Client Secret**.
3. В `config.toml`:

   ```toml
   [twitch]
   enabled = true
   client_id = "..."
   client_secret = "..."
   include_follows = false
   ```

4. При первом запуске откроется страница Twitch для авторизации — подтверди.
   Токен сохранится локально и будет обновляться автоматически.

Скоупы запрашиваются сами: `bits:read` (cheer) и, если `include_follows`,
`moderator:read:followers`.

### Настройка Twitch Chat (без токенов)

Чат читается публично и анонимно через официальный Twitch IRC WebSocket. Регистрация приложения не требуется. В `config.toml`:

```toml
[twitch_chat]
enabled = true
channel = "твой_канал"
```

При запуске мост подключится к чату, и оверлей `src/overlays/chat.html` начнёт выводить сообщения в реальном времени.

### Настройка DonationAlerts

1. Создай приложение на https://www.donationalerts.com/application/clients
   (redirect: `http://localhost`).
2. Получи access token со scope `oauth-donation-subscribe`
   (https://www.donationalerts.com/apidoc).
3. В `config.toml`:

   ```toml
   [donationalerts]
   enabled = true
   access_token = "..."
   ```

### Запуск

```bash
./.venv/bin/python alerts_bridge.py
```

Логи покажут подключение адаптеров и адрес WebSocket. Оверлей `alerts.html`
подключается автоматически при старте; без моста он молчит и переподключается.

### Автозапуск (systemd user unit)

```ini
~/.config/systemd/user/system-bridge.service
[Unit]
Description=SYSTEM alerts bridge

[Service]
WorkingDirectory=%h/OBS-Templates/bridge
ExecStart=%h/OBS-Templates/bridge/.venv/bin/python alerts_bridge.py
Restart=on-failure

[Install]
WantedBy=default.target
```

```bash
systemctl --user enable --now system-bridge.service
```

### Проверка без внешних сервисов

```bash
curl -X POST http://127.0.0.1:8787/notify \
  -H 'Content-Type: application/json' \
  -d '{"kind": "raid", "user": "tester · 42 viewers"}'
```

Или прямо в браузере: `alerts.html?demo=loop` гоняет все типы событий.

## Кастомизация

Все визуальные константы — в `src/tokens/tokens.css`. Меняются только там.

| Роль | Значение | Назначение |
|---|---|---|
| `--color-base` | `#0B0F14` | фон сцены |
| `--color-surface` | `#151C24` | панели |
| `--color-surface-raised` | `#1B242E` | приподнятые элементы |
| `--color-accent` | `#63E6BE` | активные состояния, прогресс |
| `--color-warning` | `#E9B13C` | starting / brb |
| `--color-danger` | `#E5484D` | ошибки |

Геометрия: строгая TUI-геометрия (в стиле system24: прямые углы 0px, границы 1px, safe area 32px). Motion: fast
180ms, normal 280ms, scene 500ms.

Внимание: **Space Grotesk не содержит кириллицу** — display-текст только
латиницей.

Шрифты лежат в `src/fonts/` и подключаются локально (`src/base/fonts.css`);
если в системе установлен IBM Plex Mono, используется системный. Интернет в
OBS не нужен.

## Устранение неполадок

| Симптом | Причина / решение |
|---|---|
| Browser source чёрный или пустой | проверь галочку Local file и полный путь; размер источника должен быть 1920×1080; сделай Refresh источника |
| Шрифт выглядит не так | шрифты бандлятся локально; убедись что не переименовал `src/fonts/`; при кастомных токенах проверь `--font-*` |
| Алерты не приходят от Twitch | `GET http://127.0.0.1:8787/health` — статус адаптеров; проверь логи моста; токен мог протухнуть — удали сохранённый токен и перезапусти |
| Оверлей «не видит» мост | мост запущен? порт 8787 свободен? другой адрес задаётся `?ws=<url>`, отключение — `?ws=off` |
| Изменил css, в OBS ничего не поменялось | Refresh источника; при Local file OBS может кэшировать — Refresh обязателен |

## Разработка

Кратко (детали и обоснования — в [`docs/`](docs/)):

- **Компонент**: css в `src/components/`, префикс классов имени, значения
  только из `tokens.css`; js рядом (`countdown.js` — образец).
- **Сцена-превью**: `src/scenes/<name>.html` + `.css`; раскладка утилитами
  `.ui--tl/tr/tc/center/stack`.
- **Оверлей**: скопируй каркас любого файла из `src/overlays/` — `overlay.css`
  + `overlay.js` дают холст 1920×1080 и якорение `?pos=`.
- **Адаптер моста**: модуль в `bridge/adapters/` c async-функцией
  `run(config, broadcast)`; нормализация через `adapters/base.normalize`.

## Лицензия

Проект распространяется по лицензии
**[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)**
(Attribution–NonCommercial–ShareAlike):

- **Attribution** — при использовании указать авторство и ссылку на репозиторий
- **NonCommercial** — коммерческое использование запрещено
- **ShareAlike** — производные распространяются под той же лицензией

Полный юридический текст — в файле [`LICENSE`](LICENSE).
