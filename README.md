# SYSTEM — OBS broadcast templates

TUI-inspired визуальная система для стрима: эфир как интерфейс технической
системы, который меняет состояние (starting → intro → main → chatting → brb →
ending). Спокойный тёмный UI, моноширинная типографика, реакция на события.

Полная концепция и дизайн-принципы: [Design and branding.md](Design%20and%20branding.md).

## Структура проекта

```
obs-templates/
├── src/
│   ├── tokens/          # design tokens (цвет, типографика, геометрия, motion)
│   │   └── tokens.css
│   ├── base/            # базовые стили
│   │   ├── fonts.css    # @font-face для локальных шрифтов
│   │   ├── reset.css    # сброс + .stage 1920×1080
│   │   ├── overlay.css  # прозрачный холст оверлеев 1920×1080 + якоря .overlay--*
│   │   └── typography.css
│   ├── components/      # переиспользуемые компоненты (css + js)
│   ├── overlays/        # прозрачные browser source для OBS (по одному на компонент)
│   ├── scenes/          # превью-чертежи сцен (полная композиция 1920×1080)
│   ├── preview/         # тест-стенд токенов и компонентов
│   └── fonts/           # локальные woff2 (Space Grotesk, IBM Plex Mono)
├── Design and branding.md
└── Design plan.md
```

## Быстрый старт

```bash
cd obs-templates
python3 -m http.server 8000
```

- Тест-стенд: http://localhost:8000/src/preview/ (живой: алерты, countdown,
  прогресс трека, смена состояний — всё крутится в loop)
- Сцены: http://localhost:8000/src/scenes/main.html (навигация в шапке)

Открыть можно и напрямую через `file://` — все пути относительные, шрифты
локальные, интернет не нужен.

## Дизайн-токены

Все значения в `src/tokens/tokens.css`. Меняются только там.

| Роль | Значение | Назначение |
|---|---|---|
| `--color-base` | `#0B0F14` | фон сцены |
| `--color-surface` | `#151C24` | панели |
| `--color-surface-raised` | `#1B242E` | приподнятые элементы |
| `--color-accent` | `#63E6BE` | активные состояния, прогресс |
| `--color-warning` | `#E9B13C` | starting / brb |
| `--color-danger` | `#E5484D` | ошибки |
| `--font-display` | Space Grotesk | заголовки, бренд (без кириллицы!) |
| `--font-interface` | IBM Plex Mono | данные, статусы, UI |

Геометрия: радиус панелей 8px, границы 1px, safe area 32px, шкала отступов
4–48px. Motion: fast 180ms, normal 280ms, scene 500ms.

Внимание: **Space Grotesk не содержит кириллицу** — display-текст только
латиницей, иначе выпадет на запасной шрифт.

## Сцены (превью)

`src/scenes/*.html` — чертежи полной композиции. Захват игры/камеры показан
плейсхолдерами; в OBS они заменяются реальными источниками.

| Файл | Композиция |
|---|---|
| `starting.html` | мерж starting+intro: развёрнутый плеер с лирикой слева, компактный countdown справа-сверху, справа колонка chat + live feed |
| `main.html` | игра на весь экран, справа колонка: плеер+live feed, чат, камера снизу |
| `chatting.html` | камера (vtube) на весь экран без фона, слева плеер+фид, справа чат |
| `focus.html` | игра почти на весь экран, маленькая камера, минимум UI |
| `break.html` | PAUSED / BRB в центре с компактным плеером, по сторонам чат и live feed |
| `ending.html` | итоговая карточка, next stream, ссылки, SYSTEM OFFLINE |

## Оверлеи для OBS

Каждый файл — самостоятельный прозрачный browser source размером 1920×1080.
Компонент позиционируется URL-параметром `?pos=`, а не перемещением источника.

| Файл | Параметры | Описание |
|---|---|---|
| `background.html` | — | фон `.bg` + HUD-уголки (нижний слой) |
| `scene-indicator.html` | `?state=` | индикатор состояния: `offline`, `starting`, `intro`, `main`, `chatting`, `focus`, `brb`, `ending` |
| `now-playing.html` | `?variant=compact\|expanded`, `expanded` центрируется сам | виджет трека |
| `activity-feed.html` | — | лента донатов/сабов/рейдов |
| `chat.html` | — | стилизованный чат |
| `countdown.html` | `?minutes=10` | обратный отсчёт (тикает клиентски) |
| `activity-pulse.html` | — | индикатор активности |
| `alerts.html` | `?demo=once\|loop`, `?hold=`, `?max=`, `?ws=` | движок алертов: FIFO-очередь, ASCII-анимация (spinner + печать заголовка + прогресс-бар), стек до `max` штук; старые сдвигаются вниз при появлении новых. Авто-подключение к мосту `ws://127.0.0.1:8787/events` (`?ws=off` выключить, `?ws=<url>` другой адрес) |

Общие параметры для всех, кроме `background.html`:

```
?pos=top-left | top-center | top-right | bottom-left | bottom-center | bottom-right | center
```

Примеры:

```
src/overlays/now-playing.html?variant=compact&pos=bottom-left
src/overlays/scene-indicator.html?state=brb&pos=top-left
src/overlays/countdown.html?minutes=15&pos=center
```

## Настройка в OBS

1. **Browser Source** → включить *Local file* → указать полный путь к
   `src/overlays/<компонент>.html`. Либо через URL локального сервера
   (`http://localhost:8000/src/overlays/...`) — тогда правки подхватываются по Refresh.
2. **Ширина/высота источника: 1920 × 1080** — холст страницы фиксированный,
   источник просто масштабируется. Не ставить 800×600 по умолчанию.
3. Custom CSS можно оставить дефолтным — прозрачность фона уже встроена в
   `base/overlay.css`.
4. Порядок слоёв снизу вверх:
   `background → game capture / vtube → camera → chat → activity-feed → now-playing → scene-indicator → activity-pulse → alerts`
5. После правок файлов — Refresh источника (ПКМ по источнику → Refresh).

### Сборка сцен

| Сцена OBS | Источники |
|---|---|
| Main | game capture (весь экран), chat, activity-feed, now-playing(compact), camera, scene-indicator(`?state=main`), pulse |
| Chatting | background (за vtube), vtube-модель (весь экран), chat, activity-feed, now-playing(compact), scene-indicator(`?state=chatting`), pulse |
| Focus | game capture, маленькая камера, scene-indicator(`?state=focus`) |
| Starting soon / Intro | background, now-playing(`?variant=expanded&pos=center-left`), countdown(`?minutes=`), chat, activity-feed, scene-indicator(`?state=starting` или `intro`), pulse |
| Break | background, chat, activity-feed, now-playing(compact, центр), scene-indicator(`?state=brb`), pulse |
| Ending | background, ending-card*, scene-indicator(`?state=ending`) |

\* ending-card пока существует только в превью сцены — при необходимости
вынесется в отдельный оверлей.

## Разработка

**Добавить компонент:** css-файл в `src/components/`, классы с префиксом имени
(`.my-widget__part`), только переменные из `tokens.css`. При необходимости js
рядом (`countdown.js` как образец).

**Добавить сцену-превью:** `src/scenes/<name>.html` + `<name>.css`; подключить
`fonts/tokens/reset/typography/scenes.css` + нужные компоненты; раскладка через
утилиты `.ui--tl/tr/bl/br/tc/center/stack`.

**Добавить оверлей:** скопировать каркас любого файла из `src/overlays/`
(`overlay.css` + `overlay.js` дают холст 1920×1080 и якорение `?pos=`).

Проверка разметки (баланс тегов):

```bash
python3 - <<'EOF'
from html.parser import HTMLParser
import glob
class P(HTMLParser):
    def __init__(self): super().__init__(); self.stack=[]
    def handle_starttag(self,t,a):
        if t not in ('meta','link','br','img'): self.stack.append(t)
    def handle_endtag(self,t):
        assert self.stack and self.stack[-1]==t, f'mismatch {t}'
for f in glob.glob('src/**/*.html', recursive=True):
    p=P(); p.feed(open(f).read()); assert not p.stack, f
print('all ok')
EOF
```

## Шрифты

Локальные woff2 лежат в `src/fonts/`, подключаются через
`src/base/fonts.css` (`local('...')` сначала, затем url). На машине с
установленным `ttf-ibm-plex` системный IBM Plex Mono используется автоматически;
bundled-копии гарантируют одинаковый рендер на любой машине и в OBS без сети.

## Статус / roadmap

- [x] Этап 1 — концепция: токены, палитра, типографика, состояния
- [x] Этап 2 — статический прототип (тест-стенд)
- [x] Этап 3 — базовые сцены + сплит на оверлеи для OBS
- [x] Сцены Starting soon и Focus
- [x] Движок алертов в оверлее (очередь, анимации, demo-режим)
- [x] Каркас моста: WebSocket-сервер + twitch/donationalerts адаптеры
- [ ] DonateX-адаптер (сверить SignalR эндпоинты)
- [ ] Переходы между режимами, динамические фоны, данные плеера
- [ ] Этап 5 — автоматизация: OBS WebSocket, переключение сцен, события Twitch
- [ ] Этап 6 — визуальный тест на реальном эфире

## Мост алертов (bridge)

Локальный демон `bridge/`: собирает события из адаптеров и раздаёт их в
оверлеи по WebSocket (`ws://127.0.0.1:8787/events`).

| Адаптер | Источник | События | Статус |
|---|---|---|---|
| twitch | Twitch EventSub WebSocket (twitchAPI) | sub / resub / gift / cheer / raid, follow — опционально | готов |
| donationalerts | Centrifugo WS, канал `$alerts:donation` | donate | готов |
| donatex | SignalR + API-ключ из профиля | donate | заглушка (сверить эндпоинты api-docs) |

### Установка и запуск

```bash
cd bridge
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp config.example.toml config.toml
./.venv/bin/python alerts_bridge.py
```

В `config.toml` включи нужные адаптеры (`enabled = true`) и заполни ключи.
Первый запуск с `[twitch]` откроет OAuth-страницу Twitch (client_id/secret из
dev-приложения) и сохранит токен локально. Для DonationAlerts нужен access
token со scope `oauth-donation-subscribe`.

### Проверка без внешних сервисов

```bash
curl -X POST http://127.0.0.1:8787/notify \
  -H 'Content-Type: application/json' \
  -d '{"kind": "raid", "user": "tester · 42 viewers"}'
```

Оверлей `alerts.html` подключается к мосту автоматически при старте; без
моста просто молчит и переподключается. `GET /health` показывает состояние.

## Исследование: существующие решения (Этапы 4–5)

Перед написанием внешних интеграций проверено, что уже есть готового.

### Плеер (MPRIS → оверлей)

| Решение | Что это | Вердикт |
|---|---|---|
| [playerctl](https://github.com/altdesktop/playerctl) + `playerctld` | стандартный CLI/демон MPRIS: `playerctl metadata --format`, `playerctl position` | **база для нашего моста**: python-демон читает metadata+position, пишет JSON/раздаёт WebSocket |
| [albilu/obs-player-overlay](https://github.com/albilu/obs-player-overlay) | python-скрипт внутри OBS: опрос через Playerctl GI → player.json → встроенный HTTP-сервер с html | близок к нашей задаче, но нам нужен свой дизайн — взять подход как референс |
| [OBS Tuna](https://obsproject.com/forum/resources/tuna.843/) | плагин OBS, пишет метаданные трека в файл | вариант «без своего кода», но формат файла чужой и Linux-поддержка игроков ограничена |
| rsp4jack/smtcinfo.py | OBS-скрипт SMTC+MPRIS с обложкой и таймлайном | референс получения обложки/позиции |

Рекомендация: свой тонкий мост `playerctl → JSON/WebSocket → наши оверлеи`.
Дизайн у нас свой, объём кода небольшой; LRC-синхротекст всё равно ни одно
готовое решение не даёт из коробки.

### Автоматизация сцен

| Решение | Что это | Вердикт |
|---|---|---|
| [obs-websocket v5](https://github.com/obsproject/obs-websocket) | встроен в OBS 28+ (порт 4455): сцены, источники, mute и т.д. | **основа этапа 5** |
| [obsws-python](https://pypi.org/project/obsws-python) / [simpleobsws](https://github.com/IRLToolkit/simpleobsws) / [obs-websocket-js](https://github.com/obs-websocket-js) | клиентские библиотеки | python — obsws-python; js пригодится в браузерных оверлеях |
| Advanced Scene Switcher | плагин OBS: макросы и условные переключения без внешнего кода | для авто-BRB по бездействию и подобных правил |
| Streamer.bot | event-driven автоматизация Twitch→OBS | тяжеловат для наших нужд, но полезен как источник идей триггеров |

Рекомендация: obs-websocket + obsws-python для контроллера состояний;
Advanced Scene Switcher — точечно, там где не хочется писать код.

### Алерты (Twitch события)

| Решение | Что это | Вердикт |
|---|---|---|
| Twitch EventSub (WebSocket transport) | официальные события: subs, raids, cheers, follows; PubSub отключён 14.04.2025 | **наш путь**: `wss://eventsub.wss.twitch.tv/ws`, до ~10 подписок — достаточно |
| [twitchAPI](https://pytwitchapi.dev) (Python) | готовые EventSub-клиенты (webhook/websocket) | использовать в мосте вместо сырого протокола |
| [greys-tools/twitch-overlay](https://github.com/greys-tools/twitch-overlay) | self-hosted alert box с очередью (Node, SSE backend→overlay) | хорошая референс-реализация очереди и транспорта, дизайн чужой |
| Streamer.bot | event-driven автоматизация Twitch→OBS | Linux только через экспериментальный Wine — не наш путь |
| DonationAlerts Centrifugo WS | **прямой API донатов**: `wss://centrifugo.donationalerts.com/connection/websocket`, OAuth scope `oauth-donation-subscribe`; есть Node-библиотека `@donation-alerts/events` и Python-гайды | виджет не нужен — забираем данные напрямую в нашу систему |
| [DonateX API](https://donatex.gg/api-docs) | **публичные эндпоинты** с двумя формами доступа: секретный ключ стримера или OAuth 2.0; realtime через SignalR с API-ключом из профиля | второй адаптер донатов; доки — SPA, точные эндпоинты сверить при реализации моста |
| Twitch Cheer (EventSub) | нативные донаты-биты: `channel.cheer`, scope `bits:read` | покрывает биты без внешних платформ |

Рекомендация: свой движок алертов (готов, см. roadmap) поверх трёх
адаптеров моста — Twitch EventSub WebSocket (twitchAPI) для sub/raid/cheer,
DonationAlerts Centrifugo и DonateX SignalR для сторонних донатов. Все три
работают локально, без публичного URL и чужих виджетов.

## Лицензия

Проект распространяется по лицензии
**[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)**
(Attribution–NonCommercial–ShareAlike):

- **Attribution** — при использовании указать авторство и ссылку на репозиторий
- **NonCommercial** — коммерческое использование запрещено
- **ShareAlike** — производные распространяются под той же лицензией

Полный юридический текст — в файле [`LICENSE`](LICENSE).
