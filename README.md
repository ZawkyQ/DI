<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Windows-10%2F11-0078D6?style=for-the-badge&logo=windows11&logoColor=white" />
  <img src="https://img.shields.io/badge/Discord-Rich%20Presence-5865F2?style=for-the-badge&logo=discord&logoColor=white" />
</p>

<h1 align="center">Dynamic Island Mini Player</h1>

<p align="center">
  Десктопный мини-плеер в стиле Dynamic Island для Windows.<br>
  Работает с <b>любым</b> источником музыки — Яндекс Музыка, Spotify, браузер, VLC и т.д.
</p>

---

## Возможности

| | Фича | Описание |
|---|---|---|
| **島** | Dynamic Island | Анимированный оверлей с пружинной физикой, всплывает сверху экрана |
| **🎨** | Акцентный цвет | Прогресс-бар подстраивается под цвета обложки альбома |
| **🖼** | Обложка | Автоматическое извлечение и отображение с закруглёнными углами |
| **⏯** | Управление | Play/pause, next/prev, перемотка по клику на прогресс-бар |
| **🔊** | Громкость | Регулировка колёсиком мыши |
| **🎤** | Голос | Голосовые команды на русском через Vosk (офлайн) |
| **💬** | Discord RPC | Текущий трек отображается в профиле Discord |
| **📌** | Системный трей | Меню: показать, автозапуск, Discord RPC вкл/выкл, выход |

---

## Быстрый старт

### 1. Установка зависимостей

```bash
pip install customtkinter pillow winsdk pystray pypresence
```

Или просто запусти `install.bat` — он установит всё, включая опциональные пакеты.

<details>
<summary><b>Опционально: голосовое управление</b></summary>

```bash
pip install vosk sounddevice numpy
```

Скачай модель Vosk для русского языка и положи в папку `vosk-model/` в корне проекта.

</details>

### 2. Запуск (из исходников)

```bash
pythonw player.pyw
```

Или двойной клик по `run.bat`.

### 3. Сборка в .exe (опционально)

```bash
pip install pyinstaller
pyinstaller DynamicIsland.spec
```

Готовый `DynamicIsland.exe` появится в папке `dist/`. Запускай его напрямую — Python на машине не нужен.

> **Важно:** если используешь голосовое управление, папку `vosk-model/` нужно положить рядом с exe.

---

## Голосовые команды

| Команда | Действие |
|---|---|
| `стоп` / `пауза` / `стой` | Пауза |
| `играй` / `плей` / `включи` / `давай` | Воспроизведение |
| `следующий` / `дальше` / `скип` | Следующий трек |
| `предыдущий` / `назад` / `верни` | Предыдущий трек |
| `громче` / `прибавь` | Увеличить громкость |
| `тише` / `убавь` | Уменьшить громкость |

---

## Discord Rich Presence

1. Создай приложение на [Discord Developer Portal](https://discord.com/developers/applications)
2. Скопируй **Application ID** в переменную `DISCORD_APP_ID` в `player.pyw`
3. *(Опционально)* Загрузи картинки в **Rich Presence > Art Assets**:
   - `music_icon` — основная иконка
   - `play_icon` / `pause_icon` — статус воспроизведения

---

## Структура проекта

```
├── player.pyw           # Основной мини-плеер
├── install.bat          # Установка зависимостей
├── run.bat              # Быстрый запуск
└── vosk-model/          # Модель распознавания речи (скачивается отдельно)
```

---

## Технологии

| Библиотека | Назначение |
|---|---|
| `customtkinter` | UI-фреймворк |
| `Pillow` | Обработка обложек |
| `winsdk` | Системный медиа-API Windows |
| `vosk` | Офлайн-распознавание речи |
| `pypresence` | Discord Rich Presence |
| `pystray` | Системный трей |
