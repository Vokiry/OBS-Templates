# Исследования: существующие решения

Внутренний документ: анализ готовых инструментов перед написанием внешних
интеграций. Для пользовательской документации см. [README](../README.md).

## Плеер (MPRIS → оверлей)

| Решение | Что это | Вердикт |
|---|---|---|
| [playerctl](https://github.com/altdesktop/playerctl) + `playerctld` | стандартный CLI/демон MPRIS: `playerctl metadata --format`, `playerctl position` | **база для нашего моста**: python-демон читает metadata+position, пишет JSON/раздаёт WebSocket |
| [albilu/obs-player-overlay](https://github.com/albilu/obs-player-overlay) | python-скрипт внутри OBS: опрос через Playerctl GI → player.json → встроенный HTTP-сервер с html | близок к нашей задаче, но нам нужен свой дизайн — взять подход как референс |
| [OBS Tuna](https://obsproject.com/forum/resources/tuna.843/) | плагин OBS, пишет метаданные трека в файл | вариант «без своего кода», но формат файла чужой и Linux-поддержка игроков ограничена |
| rsp4jack/smtcinfo.py | OBS-скрипт SMTC+MPRIS с обложкой и таймлайном | референс получения обложки/позиции |

Рекомендация: свой тонкий мост `playerctl → JSON/WebSocket → наши оверлеи`.
Дизайн у нас свой, объём кода небольшой; LRC-синхротекст всё равно ни одно
готовое решение не даёт из коробки.

## Автоматизация сцен

| Решение | Что это | Вердикт |
|---|---|---|
| [obs-websocket v5](https://github.com/obsproject/obs-websocket) | встроен в OBS 28+ (порт 4455): сцены, источники, mute и т.д. | **основа этапа 5** |
| [obsws-python](https://pypi.org/project/obsws-python) / [simpleobsws](https://github.com/IRLToolkit/simpleobsws) / [obs-websocket-js](https://github.com/obs-websocket-js) | клиентские библиотеки | python — obsws-python; js пригодится в браузерных оверлеях |
| Advanced Scene Switcher | плагин OBS: макросы и условные переключения без внешнего кода | для авто-BRB по бездействию и подобных правил |
| Streamer.bot | event-driven автоматизация Twitch→OBS | тяжеловат для наших нужд + Linux только через экспериментальный Wine |

Рекомендация: obs-websocket + obsws-python для контроллера состояний;
Advanced Scene Switcher — точечно, там где не хочется писать код.

## Алерты (Twitch и донаты)

| Решение | Что это | Вердикт |
|---|---|---|
| Twitch EventSub (WebSocket transport) | официальные события: subs, raids, cheers, follows; PubSub отключён 14.04.2025 | **наш путь**: `wss://eventsub.wss.twitch.tv/ws`, до ~10 подписок — достаточно |
| [twitchAPI](https://pytwitchapi.dev) (Python) | готовые EventSub-клиенты (webhook/websocket) | используется в мосте вместо сырого протокола |
| [greys-tools/twitch-overlay](https://github.com/greys-tools/twitch-overlay) | self-hosted alert box с очередью (Node, SSE backend→overlay) | хорошая референс-реализация очереди и транспорта, дизайн чужой |
| Streamer.bot | event-driven автоматизация Twitch→OBS | Linux только через экспериментальный Wine — не наш путь |
| DonationAlerts Centrifugo WS | **прямой API донатов**: `wss://centrifugo.donationalerts.com/connection/websocket`, OAuth scope `oauth-donation-subscribe`; есть Node-библиотека `@donation-alerts/events` и Python-гайды | виджет не нужен — забираем данные напрямую в нашу систему |
| [DonateX API](https://donatex.gg/api-docs) | **публичные эндпоинты** с двумя формами доступа: секретный ключ стримера или OAuth 2.0; realtime через SignalR с API-ключом из профиля | второй адаптер донатов; доки — SPA, точные эндпоинты сверить при реализации адаптера |
| Twitch Cheer (EventSub) | нативные донаты-биты: `channel.cheer`, scope `bits:read` | покрывает биты без внешних платформ |
| Streamlabs / StreamElements | hosted alert box | кастомизация под наш TUI-стиль ограничена — не подходит |

Итог: свой движок алертов поверх адаптеров моста — Twitch EventSub WebSocket
(twitchAPI), DonationAlerts Centrifugo, DonateX SignalR. Все работают локально,
без публичного URL и чужих виджетов.

## Открытые вопросы

- **DonateX**: точные SignalR-эндпоинты и формат сообщений — доки в SPA,
  нужно пройти руками через donatex.gg/api-docs.
- **Сообщения зрителей** в CHEER/RESUB/DONATE: показывать ли текст в алерте
  или ограничиться суммой/месяцами. Схема события уже позволяет передать
  message, вопрос только в отображении.
- **Обложки треков**: источник artUrl для now-playing (локальные файлы vs
  проксирование) — решить на этапе плеер-адаптера.
