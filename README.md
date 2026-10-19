# tools

Skills and small tools I build for working with coding agents, published when they might be useful to someone else. Most of the code is written with Claude Code or Codex. Each tool's README says what was measured, and on what.

## Tools

| Tool | What it does |
|---|---|
| [quota-watch](quota-watch/) | Reads the weekly Claude Code and Codex limits every hour, and sends a Telegram nudge while a week is on track to expire unused. Local, macOS only, and never reads your Claude or Codex credentials. |

## Skills

| Skill | What it does |
|---|---|
| [mermaid-diagram](mermaid-diagram/) | Lets a Hermes Agent answer in Telegram with a diagram as a picture. It writes Mermaid, renders a phone-sized PNG on the host with no browser, and sends it as a photo. Install with `hermes skills install stan-voo/tools/mermaid-diagram`. |

Each skill has its own folder with a `SKILL.md`. A Hermes skill installs with `hermes skills install stan-voo/tools/<name>`, and one for Claude Code or a similar agent with `npx skills add stan-voo/tools@<name>`.

## License

MIT

---

## Українською

Скіли й невеликі інструменти, які я роблю для роботи з агентами для програмування. Публікую ті, що можуть знадобитися ще комусь. Більшість коду написана за допомогою Claude Code або Codex. У README кожного інструмента сказано, що саме і на чому я вимірював.

| Інструмент | Що робить |
|---|---|
| [quota-watch](quota-watch/) | Щогодини читає тижневі ліміти Claude Code і Codex та пише в Телеграм, поки частина тижня ще може згоріти невикористаною. Працює локально, лише на macOS, і не читає облікових даних Claude чи Codex. |

| Скіл | Що робить |
|---|---|
| [mermaid-diagram](mermaid-diagram/) | Дає агентові Hermes Agent відповідати в Телеграмі діаграмою-картинкою. Агент пише Mermaid, скрипт без браузера рендерить на сервері PNG під розмір телефона, і він приходить як фото. Встановлення: `hermes skills install stan-voo/tools/mermaid-diagram`. |

Кожен скіл має власну папку з `SKILL.md`. Скіл для Hermes встановлюється командою `hermes skills install stan-voo/tools/<name>`, а для Claude Code чи схожого агента — `npx skills add stan-voo/tools@<name>`.
