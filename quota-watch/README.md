# quota-watch

- **Two tools:** Claude Code and Codex.
- **Local, macOS only:** one Python script and a LaunchAgent on your Mac. No server or account of its own.
- **No credentials of its own:** it never opens your Claude or Codex auth files, and writes no credential anywhere. It asks each tool through that tool's own command (`claude /usage`, `codex app-server`), and those commands run on the login they already have, with the same access as always: quota-watch does not sandbox them. It loads the whole of Claude Code's `~/.claude.json` to pick out one key, `cachedUsageUtilization` (percentages and reset times), and keeps nothing else from it. When the app-server can't answer, and on the first run to seed history, it reads Codex's local session logs, which hold your conversations, and keeps only the rate-limit numbers. The only secret it handles is the Telegram bot token you give it, to send the messages.
- **Audited:** Astra's [safety review](SAFETY-REVIEW.md) of 21 September 2026 found no critical or high-severity security issue. It found five other defects. One is fixed, and four are still open, listed under [Limits](#limits).

**A weekly allowance that resets at 77% is 23% of a subscription thrown away.** The limit resets whether you used it or not.

I measured this before building anything. My Codex week ending 19 September 2026 closed at 77%. My Claude Code week ending 21 September closed at 85%.

quota-watch reads both weekly limits every hour. It projects where each week will close at the pace so far, and sends a Telegram message while there are still days left to spend the difference.

[Українська версія нижче](#українською)

## What it does

Every hour it:

1. **Reads the weekly limits.** For Claude Code it runs Claude Code's own `/usage` in print mode. That refreshes the usage cache Claude Code keeps in `~/.claude.json`, and quota-watch reads the all-models weekly limit from it, plus any model-scoped one (Fable) and the 5-hour window. For Codex it asks the Codex app-server (`account/rateLimits/read`).
2. **Records each reading** in `~/.local/state/quota-watch/history.jsonl`.
3. **Projects the close of each week** with two paces: the average since the window opened, and the last 24 hours from history. It judges on the busier of the two, so a nudge means even your heavier recent habit leaves quota on the table.
4. **Sends a nudge** if a checkpoint is due.

Neither read spends quota. The `/usage` run reports `num_turns 0`, zero tokens and $0. quota-watch opens no auth file. Claude Code and Codex each answer on their own login.

## How it notifies you

Three kinds of Telegram message from your own bot: the weekly nudge, a warning when a limit is about to run out early, and a smaller 5-hour window nudge. The last two are described further down. The weekly one goes out at 96, 48, 24 and 10 hours before a reset, each checkpoint at most once a week, and only when at least 15 points are on track to expire. Between 23:00 and 08:00 the message arrives silently. If Telegram is not configured, or the send fails, you get a macOS notification instead. When several are due at once they come as one message: Claude first, its 5-hour window at the top, then Codex.

It stays quiet in the first 12 hours of a week, when a pace is one session's noise, and in the last 3 hours, when nothing heavy can still be scheduled. A busy week sends nothing at all. It also stays quiet when a reading could not be refreshed: a weekly nudge needs a reading less than 3 hours old, and a checkpoint skipped for that reason goes out on the next run that has one.

A weekly nudge from a simulated 48-hour checkpoint (made-up numbers). Lines marked ▍ are sent as a collapsible quote:

```
⏳ Codex: ~79% of this week will go unused
Resets Wed 23 Sep 18:38

▍ 15% used · pace 3.0%/day → ~21% at reset
▍ To use it all: 42.5%/day, 14.2× your pace
```

The headline says where the week stands. The quote holds the numbers behind it: where your pace lands, and what would use all of it, measured against your own pace. "14.2× your pace" means a normal week won't close this gap.

`status --telegram` sends the same view on demand: Claude first, its 5-hour window above its week, then Codex. The numbers in this one are real, from two and a half hours after my Claude week reset:

```
Usage limits · Mon 18:37

⏱ Claude 5h window: 7% used
Resets 22:00, in 3h 22m

On pace: no need to push.

Claude · too early
Resets Mon 28 Sep 16:00

▍ 5% used, 2h 37m into the week
▍ To use it all: 13.8%/day, 1.1× last week's 12%/day (it ended at 85%)
▍ Fable 6%

Codex · behind
Resets Sat 26 Sep 16:20

▍ 8% used · pace 3.8%/day → ~27% at reset
▍ To use it all: 18.8%/day, 4.9× your pace
```

The line under the 5-hour window is advice for that window, judged against its week: "A good moment to start something heavy" while the week is behind and the window at least half unused, "Keep going: the week is still behind" once the window is more than half used, "Go easy: the week is on course to run out before its reset", or "On pace: no need to push". A week too young for a pace is judged by last week's.

When a reading could not be refreshed, its block says so after its numbers and gives no advice. A real one, from a run just after my Mac rebooted: "Codex numbers are from Mon 21 Sep 19:22: the live check failed".

The verdict after each name is one of: **behind** (15 points or more on track to go unused), **close** (5 to 15), **on track**, **ahead** (it will run out before the reset, and the message gives the daily rate that would last), or **too early** (under 12 hours into the week, so the comparison is with last week's pace). `status -v` adds a one-row-per-limit table and the working behind every number.

**Which Claude limit leads.** By default, Claude's messages follow the all-models limit. Some people run out of one model first; for me that's Fable. `QUOTA_WATCH_CLAUDE_LIMIT=fable` makes the Fable limit lead Claude's block and every Claude nudge, and moves all models into the quote.

**Running out early.** The leading limit gets one more message: a warning when it is on course to run out at least 6 hours before its reset. It comes once when first seen and once more within a day of running out. It gives the daily rate that would last, and says whether other models still have room (made-up numbers):

```
⚠️ Claude Fable will run out 2d 17h before its reset
Resets Fri 25 Sep 18:35

All models is at 40%: move work to other models

▍ 70% used · pace 23.3%/day → runs out ~Wed 23 Sep 01:35
▍ To last until reset: ≤ 7.5%/day, 0.3× your pace
▍ 5h window 20%, resets 19:54
```

In `status` the 5-hour window sits above its week, and in a nudge it goes in the quote. It caps how fast you can spend the week, so its first job is sizing. Once history holds a full window's worth of 5-hour movement, quota-watch measures how much of the week one full 5-hour window is worth, and states the gap in windows, in the quote: "≈ 1.9 full 5h windows a day". My Codex plan (prolite) currently reports no 5-hour window. If yours has one, it shows up the same way.

Its second job is a smaller nudge. A window's unused part is gone when it resets, and while the week is behind, that is capacity you can't get back. So when a 5-hour window resets within 90 minutes with at least half of it unused, and the week is behind by the same 15-point test, you get (made-up numbers):

```
⏱ Claude 5h window: 70% unused
Resets 19:26, in 1h 09m

The Claude week (resets Mon 28 Sep 16:00) is on track to leave ~77% unused.

A good moment to start something heavy.
```

The header names only the tool, because Claude reports one 5-hour window with no model attached. The next line names the week the window is measured against. With `QUOTA_WATCH_CLAUDE_LIMIT=fable`, that is "The Claude Fable week".

At most once per window, never between 23:00 and 08:00, never while the week is on pace, and never on a reading more than an hour old. `QUOTA_WATCH_WINDOW_NUDGES=0` turns it off.

## Why this and not codenotch

[codenotch](https://github.com/vinzdg/codenotch) is a good app, and I borrowed from it. The `/usage` flags that make a Claude reading free come from its `ClaudeUsageCLI.swift`. It pins usage rings for about twenty providers to a screen edge, and alerts you when a limit crosses 80% or reaches 100%.

Those alerts protect you from running out. My problem ran the other way: both weeks ended with quota unused, and codenotch has nothing that fires for that. It alerts at 80%, at 100% and at reset. Its pace line ("deficit" or "reserved", used minus elapsed) describes today's gap, on screen, if you happen to look.

quota-watch differs in four ways. I suspect they matter only for this one job:

- **It looks ahead.** It projects each week to its reset, nudges on under-use, and warns when the leading limit will run out early. codenotch alerts on the level itself, at 80% and 100%.
- **It keeps a history,** so it knows the last day's pace and how last week closed. codenotch remembers only the last reading, to survive a restart.
- **It reaches your phone.** A macOS notification disappears if you are away from the Mac. A Telegram message waits for you.
- **It reads Codex without touching its token.** codenotch reads each Codex profile's `auth.json`. quota-watch asks the Codex app-server, which answers on Codex's own login.

codenotch is plainly better at everything else: a glanceable view, many providers, several accounts, live 5-hour-window alerts, a signed app. For watching your limits, I'd pick codenotch. For weeks that keep ending with quota left over, quota-watch does a job codenotch doesn't attempt. Nothing stops you running both.

## Limits

- **Four known defects.** Astra's [safety review](SAFETY-REVIEW.md) found five on 21 September 2026. One is fixed: a nudge could recommend heavy work on hours-old readings (finding 2). Four are open. The Codex read can hang past its timeout or miss a reply. A failed notification is still marked as sent, and never retried. `CODEX_HOME` or `CLAUDE_CONFIG_DIR` set only in `~/.config/quota-watch/env` doesn't reach `claude` or `codex`, so a reading can come from the wrong account. A reinstall from a path containing characters like `&` can leave the LaunchAgent stopped. The review's advice: fix them before depending on unattended monitoring.
- **Two tools.** Claude Code and Codex. A 5-hour window nudges only while its week is behind; on a week that's on pace it stays silent.
- **Hourly ticks can miss a window.** The window nudge needs a tick inside the 90 minutes before a reset. A Mac asleep through that stretch sends nothing, and so does a tick that can't refresh the reading.
- **The windows-per-day figure needs data.** It stays hidden until history holds at least one full window's worth of 5-hour movement, and it assumes the week-to-window ratio holds steady. Both limits report whole percents, so treat it as approximate.
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
python3 quota_watch.py status               # where each week stands, and what would use it all
python3 quota_watch.py status -v            # plus a one-row-per-limit table and the working
python3 quota_watch.py status --telegram    # the same, sent to Telegram
python3 quota_watch.py tick --dry-run       # print the nudge a tick would send now
python3 quota_watch.py backfill             # seed history from Codex's session logs
```

All optional, in the environment or in `~/.config/quota-watch/env`:

| Setting | Default | Meaning |
|---|---|---|
| `QUOTA_WATCH_CLAUDE_LIMIT` | `all` | The Claude limit that leads messages and nudges: `all`, or a model such as `fable` |
| `QUOTA_WATCH_GAP` | `15` | Points on track to expire before a nudge |
| `QUOTA_WATCH_CHECKPOINTS` | `96,48,24,10` | Hours before a reset when a nudge may fire |
| `QUOTA_WATCH_QUIET` | `23-8` | Local hours when Telegram delivers silently, and window nudges are skipped |
| `QUOTA_WATCH_WINDOW_NUDGES` | `1` | `0` turns off the 5-hour window nudge |
| `QUOTA_WATCH_WINDOW_LEAD` | `90` | Minutes before a 5-hour reset when a window nudge may fire |
| `QUOTA_WATCH_WINDOW_ROOM` | `50` | Percent of the window that must be unused |
| `CLAUDE_BIN`, `CODEX_BIN` | found automatically | Binaries, if they are not where they install |
| `QUOTA_WATCH_ENV_FILE` | `~/.config/quota-watch/env` | Where settings are read from |

---

## Українською

- **Два інструменти:** Claude Code і Codex.
- **Локально, лише macOS:** один Python-скрипт і LaunchAgent на вашому Маку. Жодного власного сервера чи акаунта.
- **Жодних власних облікових даних:** він не відкриває файлів авторизації Claude чи Codex і ніде не записує облікових даних. Кожен інструмент він питає через його власну команду (`claude /usage`, `codex app-server`), а ці команди працюють на вже наявному логіні з тим самим доступом, що й завжди: quota-watch їх не ізолює. Файл Claude Code `~/.claude.json` він завантажує цілком, щоб узяти один ключ, `cachedUsageUtilization` (відсотки й час скидання), і нічого іншого звідти не зберігає. Коли app-server не відповідає, а також під час першого запуску, щоб заповнити історію, він читає локальні логи сесій Codex, де зберігаються ваші розмови, і бере з них лише цифри лімітів. Він торкається лише одного секрету: токена Телеграм-бота, який ви самі даєте йому для надсилання повідомлень.
- **Перевірено:** [аудит безпеки](SAFETY-REVIEW.md) від Astra 21 вересня 2026 року не знайшов критичних чи серйозних проблем безпеки. Він знайшов п'ять інших вад. Одну виправлено, чотири ще ні: вони в розділі [Обмеження](#обмеження).

**Якщо тижневий ліміт скинувся на 77%, то 23% підписки пішли на смітник.** Ліміт скидається незалежно від того, використали ви його чи ні.

Перш ніж щось будувати, я це виміряв. Мій тиждень у Codex закрився 19 вересня 2026 року на 77%. Тиждень у Claude Code закрився 21 вересня на 85%.

quota-watch щогодини читає обидва тижневі ліміти. Рахує, де закриється кожен тиждень, якщо темп збережеться, і пише в Телеграм, поки ще лишаються дні, щоб витратити різницю.

## Що він робить

Щогодини він:

1. **Читає тижневі ліміти.** Для Claude Code запускає його ж команду `/usage` у print-режимі. Вона оновлює кеш використання, який Claude Code тримає в `~/.claude.json`, і quota-watch бере звідти загальний тижневий ліміт на всі моделі, а також окремий ліміт на модель (Fable), якщо він є, і п'ятигодинне вікно. Для Codex питає Codex app-server (`account/rateLimits/read`).
2. **Записує кожне показання** в `~/.local/state/quota-watch/history.jsonl`.
3. **Прогнозує, як закриється тиждень,** за двома темпами: середнім від початку вікна і за останні 24 години з історії. Орієнтується на вищий із двох. Тож нагадування означає, що навіть ваш інтенсивніший останній темп лишає квоту невикористаною.
4. **Надсилає нагадування,** якщо настала контрольна точка.

Жодне читання не витрачає квоту. Запуск `/usage` показує `num_turns 0`, нуль токенів і $0. quota-watch не відкриває файлів авторизації. Claude Code і Codex відповідають кожен через власний логін.

## Як він вас сповістить

Трьома видами повідомлень у Телеграмі від вашого власного бота: тижневим нагадуванням, попередженням, що квота закінчиться раніше, і меншим нагадуванням про п'ятигодинне вікно. Останні два описані нижче. Тижневе приходить за 96, 48, 24 і 10 годин до скидання ліміту. Кожна точка спрацьовує не частіше разу на тиждень, і лише тоді, коли за прогнозом згорить щонайменше 15 пунктів. З 23:00 до 08:00 повідомлення приходить беззвучно. Якщо Телеграм не налаштований або надіслати не вдалося, замість нього з'явиться сповіщення macOS. Якщо кілька нагадувань припадають на один запуск, вони приходять одним повідомленням: спершу Claude з п'ятигодинним вікном угорі, потім Codex.

Перші 12 годин тижня він мовчить, бо за такий час темп відбиває хіба одну сесію. Останні 3 години теж мовчить, бо щось важке ви вже не встигнете запланувати. За інтенсивного тижня повідомлень не буде взагалі. Він мовчить і тоді, коли показання не вдалося оновити. Тижневому нагадуванню потрібне показання, якому менше 3 годин, а точка, пропущена з цієї причини, спрацює на першому ж запуску зі свіжим показанням.

Тижневе нагадування із симуляції точки за 48 годин до скидання (цифри вигадані). Рядки з позначкою ▍ надсилаються як цитата, яку можна згорнути:

```
⏳ Codex: ~79% of this week will go unused
Resets Wed 23 Sep 18:38

▍ 15% used · pace 3.0%/day → ~21% at reset
▍ To use it all: 42.5%/day, 14.2× your pace
```

Заголовок каже, де зараз тиждень. У цитаті зібрано цифри, з яких він випливає: де ви опинитеся за такого темпу і скільки треба, щоб використати все, порівняно з вашим власним темпом. «14.2× your pace» означає, що звичайний тиждень цей розрив не закриє.

`status --telegram` надсилає цю ж картину на вимогу: спершу Claude з п'ятигодинним вікном над його тижнем, потім Codex. Цифри тут справжні, зняті через дві з половиною години після скидання мого тижня в Claude:

```
Usage limits · Mon 18:37

⏱ Claude 5h window: 7% used
Resets 22:00, in 3h 22m

On pace: no need to push.

Claude · too early
Resets Mon 28 Sep 16:00

▍ 5% used, 2h 37m into the week
▍ To use it all: 13.8%/day, 1.1× last week's 12%/day (it ended at 85%)
▍ Fable 6%

Codex · behind
Resets Sat 26 Sep 16:20

▍ 8% used · pace 3.8%/day → ~27% at reset
▍ To use it all: 18.8%/day, 4.9× your pace
```

Рядок під п'ятигодинним вікном дає пораду саме щодо цього вікна з огляду на його тиждень: «A good moment to start something heavy», поки тиждень відстає, а вікно використане не більше ніж наполовину; «Keep going: the week is still behind», коли вікно використане більше ніж наполовину; «Go easy: the week is on course to run out before its reset»; або «On pace: no need to push». Якщо тиждень надто молодий і темпу ще немає, його оцінюють за темпом минулого тижня.

Якщо показання не вдалося оновити, блок каже про це після своїх цифр і не дає порад. Справжній приклад із запуску одразу після перезавантаження мого Мака: «Codex numbers are from Mon 21 Sep 19:22: the live check failed».

Після назви стоїть вердикт: **behind** (за прогнозом згорить 15 пунктів і більше), **close** (від 5 до 15), **on track** (іде за планом), **ahead** (квота закінчиться до скидання, і повідомлення підкаже денну норму, якої вистачить) або **too early** (минуло менше 12 годин тижня, тож порівняння йде з темпом минулого тижня). `status -v` додає таблицю по рядку на ліміт і розрахунок за кожним числом.

**Який ліміт Claude головний.** Типово повідомлення про Claude стежать за лімітом на всі моделі. Дехто спершу вичерпує ліміт окремої моделі, у мене це Fable. `QUOTA_WATCH_CLAUDE_LIMIT=fable` робить ліміт Fable головним у блоці Claude і в усіх нагадуваннях про Claude, а ліміт на всі моделі переходить у цитату.

**Квота закінчиться раніше.** Головний ліміт отримує ще одне повідомлення: попередження, коли за прогнозом він вичерпається щонайменше за 6 годин до скидання. Воно приходить раз, коли це вперше видно, і ще раз протягом доби до вичерпання. У ньому є денна норма, якої вистачить до скидання, і сказано, чи лишилось місце в інших моделях (цифри вигадані):

```
⚠️ Claude Fable will run out 2d 17h before its reset
Resets Fri 25 Sep 18:35

All models is at 40%: move work to other models

▍ 70% used · pace 23.3%/day → runs out ~Wed 23 Sep 01:35
▍ To last until reset: ≤ 7.5%/day, 0.3× your pace
▍ 5h window 20%, resets 19:54
```

У `status` п'ятигодинне вікно стоїть над своїм тижнем, а в нагадуванні потрапляє в цитату. Воно обмежує, як швидко можна витрачати тиждень, тож перша його робота в тому, щоб перевести норму в зрозумілі одиниці. Щойно в історії набереться рух на ціле п'ятигодинне вікно, quota-watch виміряє, скільки тижня коштує одне повне вікно, і покаже розрив у вікнах, у цитаті: «≈ 1.9 full 5h windows a day». Мій план Codex (prolite) зараз п'ятигодинного вікна не має. Якщо ваш має, воно з'явиться так само.

Друга його робота полягає в меншому нагадуванні. Невикористана частина вікна згорає при скиданні, і поки тиждень відстає, цю ємність уже не повернути. Тож коли п'ятигодинне вікно скидається протягом 90 хвилин, щонайменше половина його не використана, а тиждень відстає за тим самим правилом 15 пунктів, приходить таке (цифри вигадані):

```
⏱ Claude 5h window: 70% unused
Resets 19:26, in 1h 09m

The Claude week (resets Mon 28 Sep 16:00) is on track to leave ~77% unused.

A good moment to start something heavy.
```

У заголовку стоїть лише назва інструмента, бо п'ятигодинне вікно в Claude одне й не прив'язане до жодної моделі. Наступний рядок називає тиждень, з яким порівнюють вікно. З `QUOTA_WATCH_CLAUDE_LIMIT=fable` це «The Claude Fable week».

Не частіше разу на вікно, ніколи з 23:00 до 08:00, ніколи, якщо тиждень іде за планом, і ніколи на підставі показання, якому понад годину. `QUOTA_WATCH_WINDOW_NUDGES=0` його вимикає.

## Чому це, а не codenotch

[codenotch](https://github.com/vinzdg/codenotch) зроблений добре, і я дещо в нього позичив. Прапорці `/usage`, завдяки яким читання ліміту Claude нічого не коштує, взяті з його `ClaudeUsageCLI.swift`. Він показує кільця використання для близько двадцяти провайдерів на краю екрана і попереджає, коли ліміт перетинає 80% або досягає 100%.

Ці попередження рятують від того, що квота закінчиться. У мене проблема протилежна: обидва тижні закрились із невикористаною квотою, а в codenotch на це нічого не спрацьовує. Він сповіщає на 80%, на 100% і при скиданні. Його рядок темпу («deficit» або «reserved», тобто використане мінус минулий час) показує сьогоднішній розрив на екрані, якщо ви туди глянете.

quota-watch відрізняється чотирма речами. Підозрюю, що важать вони лише для цієї однієї задачі:

- **Дивиться вперед.** Прогнозує кожен тиждень до скидання, нагадує про недовикористання і попереджає, що головний ліміт закінчиться раніше. codenotch реагує на сам рівень: 80% і 100%.
- **Зберігає історію,** тож знає темп за останню добу і те, як закрився минулий тиждень. codenotch пам'ятає лише останнє показання, щоб пережити перезапуск.
- **Доходить до телефона.** Сповіщення macOS зникає, якщо ви не біля Мака. Повідомлення в Телеграмі дочекається.
- **Читає Codex, не чіпаючи його токена.** codenotch читає `auth.json` кожного профілю Codex. quota-watch питає Codex app-server, який відповідає через власний логін Codex.

У всьому іншому codenotch явно кращий: усе видно з першого погляду, багато провайдерів, кілька акаунтів, живі сповіщення про п'ятигодинне вікно, підписаний застосунок. Щоб стежити за лімітами, я б обрав codenotch. Якщо ж тижні раз у раз закінчуються з невикористаною квотою, quota-watch робить те, за що codenotch не береться. Ніщо не заважає запускати обидва.

## Обмеження

- **Чотири відомі вади.** [Аудит безпеки](SAFETY-REVIEW.md) від Astra знайшов п'ять 21 вересня 2026 року. Одну виправлено: нагадування могло радити важку роботу на підставі показань, яким уже кілька годин (пункт 2). Чотири лишаються. Читання Codex може не вкластися в таймаут і зависнути або пропустити відповідь. Невдале сповіщення все одно позначається як надіслане, і повторної спроби не буде. `CODEX_HOME` чи `CLAUDE_CONFIG_DIR`, задані лише в `~/.config/quota-watch/env`, не доходять до `claude` і `codex`, тож показання може прийти з іншого акаунта. Перевстановлення зі шляху, де є символи на кшталт `&`, може залишити LaunchAgent зупиненим. Порада аудиту: виправити їх, перш ніж покладатися на моніторинг без нагляду.
- **Два інструменти.** Claude Code і Codex. П'ятигодинне вікно нагадує лише тоді, коли його тиждень відстає. Якщо тиждень іде за планом, воно мовчить.
- **Щогодинні перевірки можуть проґавити вікно.** Нагадуванню про вікно потрібна перевірка в останні 90 хвилин перед скиданням. Якщо Мак у цей час спить або перевірка не змогла оновити показання, нічого не прийде.
- **Кількості вікон на день потрібні дані.** Цей рядок не з'явиться, доки в історії не набереться рух хоча б на одне повне п'ятигодинне вікно. До того ж він припускає, що співвідношення тижня й вікна стабільне. Обидва ліміти звітують цілими відсотками, тож цифра приблизна.
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
python3 quota_watch.py status               # де кожен тиждень і що використає решту
python3 quota_watch.py status -v            # плюс таблиця по рядку на ліміт і розрахунок
python3 quota_watch.py status --telegram    # те саме, в Телеграм
python3 quota_watch.py tick --dry-run       # показати нагадування, яке надіслав би запуск зараз
python3 quota_watch.py backfill             # заповнити історію з логів сесій Codex
```

Усе необов'язкове, у змінних середовища або у `~/.config/quota-watch/env`:

| Налаштування | Типово | Що означає |
|---|---|---|
| `QUOTA_WATCH_CLAUDE_LIMIT` | `all` | Який ліміт Claude головний: `all` або модель, наприклад `fable` |
| `QUOTA_WATCH_GAP` | `15` | Скільки пунктів має згоріти, щоб надіслати нагадування |
| `QUOTA_WATCH_CHECKPOINTS` | `96,48,24,10` | За скільки годин до скидання може прийти нагадування |
| `QUOTA_WATCH_QUIET` | `23-8` | Години, коли Телеграм доставляє беззвучно, а нагадувань про вікно немає зовсім |
| `QUOTA_WATCH_WINDOW_NUDGES` | `1` | `0` вимикає нагадування про п'ятигодинне вікно |
| `QUOTA_WATCH_WINDOW_LEAD` | `90` | За скільки хвилин до скидання вікна може прийти нагадування |
| `QUOTA_WATCH_WINDOW_ROOM` | `50` | Скільки відсотків вікна має лишатися невикористаним |
| `CLAUDE_BIN`, `CODEX_BIN` | визначаються автоматично | Шляхи до програм, якщо вони встановлені не там, де зазвичай |
| `QUOTA_WATCH_ENV_FILE` | `~/.config/quota-watch/env` | Звідки читати налаштування |
