# SYSTEM — Alert Sounds

В этой папке лежат звуковые эффекты для алертов (в формате `.wav` / `.mp3` / `.ogg`).

## Файлы по умолчанию:
- `donate.wav` — донат (DonationAlerts / DonateX)
- `sub.wav` — подписка / ресаб / подарочные сабы
- `raid.wav` — рейд канала
- `cheer.wav` — чиры / битсы
- `follow.wav` — фоллов
- `default.wav` — универсальный звук

## Как заменить на свои звуки:
1. Положи свои аудиофайлы в эту папку (например, `donate.mp3`, `sub.wav`).
2. Отредактируй `sounds.json` в этой папке, указав путь к файлу и громкость (от `0.0` до `1.0`):

```json
{
  "masterVolume": 0.7,
  "sounds": {
    "donate": { "file": "../sounds/donate.wav", "volume": 0.8 },
    "sub": { "file": "../sounds/sub.wav", "volume": 0.7 },
    "resub": { "file": "../sounds/sub.wav", "volume": 0.7 },
    "gift": { "file": "../sounds/sub.wav", "volume": 0.7 },
    "raid": { "file": "../sounds/raid.wav", "volume": 0.9 },
    "cheer": { "file": "../sounds/cheer.wav", "volume": 0.6 },
    "follow": { "file": "../sounds/follow.wav", "volume": 0.5 },
    "default": { "file": "../sounds/default.wav", "volume": 0.7 }
  }
}
```

## Управление через URL в OBS:
- `alerts.html?vol=0.5` — изменить общую громкость всех алертов (по умолчанию `0.7`).
- `alerts.html?sfx=off` — полностью отключить звук алертов.
