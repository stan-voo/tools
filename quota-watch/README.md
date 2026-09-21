# quota-watch

**A weekly allowance that resets at 77% is 23% of a subscription thrown away.** The limit resets whether you used it or not.

I measured this before building anything. My Codex week ending 19 September 2026 closed at 77%. My Claude Code week ending 21 September closed at 85%. From the inside, neither felt like under-use. A heavy week feels heavy.

quota-watch reads both weekly limits every hour. It projects where each week will close at the pace so far, and sends a Telegram message while there are still days left to spend the difference.

[Українська версія нижче](#українською)

## What it does

Every hour it:

1. **Reads the weekly limits.** For Claude Code it runs Claude Code's own `/usage` in print mode. That refreshes the usage cache Claude Code keeps in `~/.claude.json`, and quota-watch reads the all-models weekly limit from it, plus any model-scoped one (Fable). For Codex it asks the Codex app-server (`account/rateLimits/read`).
2. **Records each reading** in `~/.local/state/quota-watch/history.jsonl`.
3. **Projects the close of each week** with two paces: the average since the window opened, and the last 24 hours from history. It judges on the busier of the two, so a nudge means even your heavier recent habit leaves quota on the table.
4. **Sends a nudge** if a checkpoint is due.

Neither read spends quota. The `/usage` run reports `num_turns 0`, zero tokens and $0. quota-watch reads no token and no credential file. Claude Code and Codex each answer on their own login.

## How it notifies you

A Telegram message from your own bot. It goes out at 96, 48, 24 and 10 hours before a reset, each checkpoint at most once a week, and only when at least 15 points are on track to expire. Between 23:00 and 08:00 the message arrives silently. If Telegram is not configured, or the send fails, you get a macOS notification instead.

It stays quiet in the first 12 hours of a week, when a pace is one session's noise, and in the last 3 hours, when nothing heavy can still be scheduled. A busy week sends nothing at all.

A nudge, rendered from a simulated Thursday checkpoint:

```
⏳ Codex: ~86% of this week will go unused
10% used · ~14% at reset · 1d 23h left
Need 45.8%/day to use it all
Last week 77%
```

The line I plan against is "Need 45.8%/day". It turns "there's some spare quota" into a daily rate, which is what a schedule is made of.

`status --telegram` sends the whole picture on demand, one row per limit. This one is real, from half an hour after my Claude week reset:

```
Weekly limits · Mon 16:35

         used   end   left  need/d
Claude     3%   new  6d23h     14%
 Fable     5%
Codex      7%  ~24%  4d23h     19%

last week: Claude 85% · Fable 64% · Codex 77%
Codex full reset credit until 05 Oct
```

`end` is the projected close, `new` means the week is too young for a pace, and `need/d` is the daily rate that would use the rest.

## Why this and not codenotch

[codenotch](https://github.com/vinzdg/codenotch) is a good app, and I borrowed from it. The `/usage` flags that make a Claude reading free come from its `ClaudeUsageCLI.swift`. It pins usage rings for about twenty providers to a screen edge, and alerts you when a limit crosses 80% or reaches 100%.

Those alerts protect you from running out. My problem ran the other way: both weeks ended with quota unused, and codenotch has nothing that fires for that. It alerts at 80%, at 100% and at reset. Its pace line ("deficit" or "reserved", used minus elapsed) describes today's gap, on screen, if you happen to look.

quota-watch differs in four ways. I suspect they matter only for this one job:

- **It nudges on under-use,** projected to the reset, where codenotch warns on over-use.
- **It keeps a history,** so it knows the last day's pace and how last week closed. codenotch remembers only the last reading, to survive a restart.
- **It reaches your phone.** A macOS notification disappears if you are away from the Mac. A Telegram message waits for you.
- **It reads Codex without touching its token.** codenotch reads each Codex profile's `auth.json`. quota-watch asks the Codex app-server, which answers on Codex's own login.

codenotch is plainly better at everything else: a glanceable view, many providers, several accounts, the five-hour session window, a signed app. For watching your limits, I'd pick codenotch. For weeks that keep ending with quota left over, quota-watch does a job codenotch doesn't attempt. Nothing stops you running both.

## Limits

- **Two tools, weekly limits only.** Claude Code and Codex. The five-hour session window is ignored: it resets too often to waste much.
- **macOS.** Scheduling is a LaunchAgent, and the fallback is a macOS notification. The script is plain Python 3.9+ with no dependencies, so it should run from cron on Linux, but I have not tried it.
- **It leans on undocumented internals.** Claude Code's `cachedUsageUtilization`, and a Codex app-server method that Codex marks experimental. Either can change in any release. `status` flags any reading older than 3 hours, and `status -v` names where each one came from, so a stale number shows up as stale.
- **The projection is linear.** It assumes the rest of the week looks like the week so far, or like the last day. A holiday or a launch week breaks that. The 15-point margin absorbs small misses, not large ones.
- **Last week's close is a floor.** Readings are hourly, so usage after the last reading before a reset is never seen.
- **Codex from another machine can go unseen.** If the app-server call fails, quota-watch falls back to Codex's local session logs, which only move when Codex runs on this Mac.
- **It says how much, not what.** It has no idea which of your tasks are heavy. Deciding what to queue is still your call.
- **Tested on one machine, mine:** Claude Code 2.1.278, Codex CLI 0.154, macOS 26, over one day.

## Install

```
git clone https://github.com/stan-voo/tools.git
cd tools/quota-watch
python3 quota_watch.py status
```

`status` works with nothing configured. For Telegram, create a bot with [@BotFather](https://t.me/BotFather), send it one message, and get your chat id. Then put both in `~/.config/quota-watch/env` with an editor, so the token never lands in your shell history:

```
QUOTA_WATCH_TELEGRAM_BOT_TOKEN=<token from BotFather>
QUOTA_WATCH_TELEGRAM_CHAT_ID=<your chat id>
```

Then lock the file down, load the hourly job, and check delivery:

```
chmod 600 ~/.config/quota-watch/env
./install.sh
python3 quota_watch.py status --telegram
```

`./install.sh --remove` unloads it. `./install.sh --print` shows the LaunchAgent without installing it.

## Commands and settings

```
python3 quota_watch.py status               # one row per limit: used, projected close, need/day
python3 quota_watch.py status -v            # the same, plus the working: both paces, sources
python3 quota_watch.py status --telegram    # the same, sent to Telegram
python3 quota_watch.py tick --dry-run       # print the nudge a tick would send now
python3 quota_watch.py backfill             # seed history from Codex's session logs
```

All optional, in the environment or in `~/.config/quota-watch/env`:

| Setting | Default | Meaning |
|---|---|---|
| `QUOTA_WATCH_GAP` | `15` | Points on track to expire before a nudge |
| `QUOTA_WATCH_CHECKPOINTS` | `96,48,24,10` | Hours before a reset when a nudge may fire |
| `QUOTA_WATCH_QUIET` | `23-8` | Local hours when Telegram delivers silently |
| `CLAUDE_BIN`, `CODEX_BIN` | found automatically | Binaries, if they are not where they install |
| `QUOTA_WATCH_ENV_FILE` | `~/.config/quota-watch/env` | Where settings are read from |

---

## Українською

**Якщо тижневий ліміт скинувся на 77%, то 23% підписки пішли на смітник.** Ліміт скидається незалежно від того, використали ви його чи ні.

Перш ніж щось будувати, я це виміряв. Мій тиждень у Codex закрився 19 вересня 2026 року на 77%. Тиждень у Claude Code закрився 21 вересня на 85%. Зсередини жоден не здавався недовикористаним. Важкий тиждень і відчувається важким.

quota-watch щогодини читає обидва тижневі ліміти. Рахує, де закриється кожен тиждень, якщо темп збережеться, і пише в Телеграм, поки ще лишаються дні, щоб витратити різницю.

## Що він робить

Щогодини він:

1. **Читає тижневі ліміти.** Для Claude Code запускає його ж команду `/usage` у print-режимі. Вона оновлює кеш використання, який Claude Code тримає в `~/.claude.json`, і quota-watch бере звідти загальний тижневий ліміт на всі моделі, а також окремий ліміт на модель (Fable), якщо він є. Для Codex питає Codex app-server (`account/rateLimits/read`).
2. **Записує кожне показання** в `~/.local/state/quota-watch/history.jsonl`.
3. **Прогнозує, як закриється тиждень,** за двома темпами: середнім від початку вікна і за останні 24 години з історії. Орієнтується на вищий із двох. Тож нагадування означає, що навіть ваш інтенсивніший останній темп лишає квоту невикористаною.
4. **Надсилає нагадування,** якщо настала контрольна точка.

Жодне читання не витрачає квоту. Запуск `/usage` показує `num_turns 0`, нуль токенів і $0. quota-watch не читає жодних токенів і жодних файлів із ключами. Claude Code і Codex відповідають кожен через власний логін.

## Як він вас сповістить

Повідомленням у Телеграмі від вашого власного бота. Воно приходить за 96, 48, 24 і 10 годин до скидання ліміту. Кожна точка спрацьовує не частіше разу на тиждень, і лише тоді, коли за прогнозом згорить щонайменше 15 пунктів. З 23:00 до 08:00 повідомлення приходить беззвучно. Якщо Телеграм не налаштований або надіслати не вдалося, замість нього з'явиться сповіщення macOS.

Перші 12 годин тижня він мовчить, бо за такий час темп відбиває хіба одну сесію. Останні 3 години теж мовчить, бо щось важке ви вже не встигнете запланувати. За інтенсивного тижня повідомлень не буде взагалі.

Ось нагадування із симуляції четвергової точки:

```
⏳ Codex: ~86% of this week will go unused
10% used · ~14% at reset · 1d 23h left
Need 45.8%/day to use it all
Last week 77%
```

Я планую за рядком «Need 45.8%/day». Він перетворює «ніби лишилась якась квота» на денну норму, а з норм і складається розклад.

`status --telegram` надсилає всю картину на вимогу, по рядку на ліміт. Цей справжній, знятий через пів години після того, як скинувся мій тиждень у Claude:

```
Weekly limits · Mon 16:35

         used   end   left  need/d
Claude     3%   new  6d23h     14%
 Fable     5%
Codex      7%  ~24%  4d23h     19%

last week: Claude 85% · Fable 64% · Codex 77%
Codex full reset credit until 05 Oct
```

`end` показує прогноз закриття тижня, `new` означає, що тиждень ще надто молодий для темпу, а `need/d` показує денну норму, яка використає решту.

## Чому це, а не codenotch

[codenotch](https://github.com/vinzdg/codenotch) зроблений добре, і я дещо в нього позичив. Прапорці `/usage`, завдяки яким читання ліміту Claude нічого не коштує, взяті з його `ClaudeUsageCLI.swift`. Він показує кільця використання для близько двадцяти провайдерів на краю екрана і попереджає, коли ліміт перетинає 80% або досягає 100%.

Ці попередження рятують від того, що квота закінчиться. У мене проблема протилежна: обидва тижні закрились із невикористаною квотою, а в codenotch на це нічого не спрацьовує. Він сповіщає на 80%, на 100% і при скиданні. Його рядок темпу («deficit» або «reserved», тобто використане мінус минулий час) показує сьогоднішній розрив на екрані, якщо ви туди глянете.

quota-watch відрізняється чотирма речами. Підозрюю, що важать вони лише для цієї однієї задачі:

- **Нагадує про недовикористання,** з прогнозом до скидання. codenotch попереджає про перевитрату.
- **Зберігає історію,** тож знає темп за останню добу і те, як закрився минулий тиждень. codenotch пам'ятає лише останнє показання, щоб пережити перезапуск.
- **Доходить до телефона.** Сповіщення macOS зникає, якщо ви не біля Мака. Повідомлення в Телеграмі дочекається.
- **Читає Codex, не чіпаючи його токена.** codenotch читає `auth.json` кожного профілю Codex. quota-watch питає Codex app-server, який відповідає через власний логін Codex.

У всьому іншому codenotch явно кращий: усе видно з першого погляду, багато провайдерів, кілька акаунтів, п'ятигодинне вікно сесії, підписаний застосунок. Щоб стежити за лімітами, я б обрав codenotch. Якщо ж тижні раз у раз закінчуються з невикористаною квотою, quota-watch робить те, за що codenotch не береться. Ніщо не заважає запускати обидва.

## Обмеження

- **Два інструменти, лише тижневі ліміти.** Claude Code і Codex. П'ятигодинне вікно сесії він ігнорує: воно скидається надто часто, щоб багато згоріло.
- **macOS.** Розклад тримається на LaunchAgent, а коли Телеграм недоступний, приходить сповіщення macOS. Сам скрипт написаний на чистому Python 3.9+ без залежностей, тож на Linux мав би працювати з cron, але я не перевіряв.
- **Спирається на незадокументовані механізми.** Це `cachedUsageUtilization` у Claude Code і метод Codex app-server, який сам Codex позначає як експериментальний. Будь-який реліз може їх змінити. `status` позначає показання, старші за 3 години, а `status -v` показує, звідки взялося кожне, тож застаріле число видно як застаріле.
- **Прогноз лінійний.** Він припускає, що решта тижня буде схожа на тиждень досі або на останню добу. Відпустка чи тиждень запуску це ламають. Запас у 15 пунктів поглинає дрібні промахи, а великі ні.
- **Цифра за минулий тиждень може бути заниженою.** Показання щогодинні, тож використання після останнього показання перед скиданням він не бачить.
- **Codex з іншої машини може лишитись непоміченим.** Якщо виклик app-server не вдався, quota-watch бере дані з локальних логів сесій Codex, а вони оновлюються лише тоді, коли Codex працює на цьому Маку.
- **Він каже скільки, а не що.** Він не знає, які з ваших задач важкі. Що поставити в чергу, вирішуєте ви.
- **Перевірено на одній машині, моїй:** Claude Code 2.1.278, Codex CLI 0.154, macOS 26, протягом одного дня.

## Встановлення

```
git clone https://github.com/stan-voo/tools.git
cd tools/quota-watch
python3 quota_watch.py status
```

`status` працює без жодних налаштувань. Для Телеграму створіть бота через [@BotFather](https://t.me/BotFather), надішліть йому одне повідомлення і дізнайтесь свій chat id. Потім запишіть обидва значення у `~/.config/quota-watch/env` через редактор, щоб токен не потрапив в історію терміналу:

```
QUOTA_WATCH_TELEGRAM_BOT_TOKEN=<токен від BotFather>
QUOTA_WATCH_TELEGRAM_CHAT_ID=<ваш chat id>
```

Далі закрийте файл від інших користувачів, запустіть щогодинну задачу і перевірте доставку:

```
chmod 600 ~/.config/quota-watch/env
./install.sh
python3 quota_watch.py status --telegram
```

`./install.sh --remove` вимикає задачу. `./install.sh --print` показує LaunchAgent, нічого не встановлюючи.

## Команди й налаштування

```
python3 quota_watch.py status               # по рядку на ліміт: використано, прогноз, норма на день
python3 quota_watch.py status -v            # те саме, плюс розрахунок: обидва темпи, джерела
python3 quota_watch.py status --telegram    # те саме, в Телеграм
python3 quota_watch.py tick --dry-run       # показати нагадування, яке надіслав би запуск зараз
python3 quota_watch.py backfill             # заповнити історію з логів сесій Codex
```

Усе необов'язкове, у змінних середовища або у `~/.config/quota-watch/env`:

| Налаштування | Типово | Що означає |
|---|---|---|
| `QUOTA_WATCH_GAP` | `15` | Скільки пунктів має згоріти, щоб надіслати нагадування |
| `QUOTA_WATCH_CHECKPOINTS` | `96,48,24,10` | За скільки годин до скидання може прийти нагадування |
| `QUOTA_WATCH_QUIET` | `23-8` | Години, коли Телеграм доставляє беззвучно |
| `CLAUDE_BIN`, `CODEX_BIN` | визначаються автоматично | Шляхи до програм, якщо вони встановлені не там, де зазвичай |
| `QUOTA_WATCH_ENV_FILE` | `~/.config/quota-watch/env` | Звідки читати налаштування |
