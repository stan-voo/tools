# Working in this repo

Public skills and small tools for working with coding agents, modelled on Simon Willison's `simonw/tools` and `simonw/skills`. Everything committed here is published: the code, the READMEs, this file and the whole git history. Write every line for a stranger reading it on GitHub.

## Layout

- **One top-level folder per item**, named with a plain noun phrase: `quota-watch/`. Tools and skills sit side by side. A folder with a `SKILL.md` is a skill, and anything else is a tool.
- **A tool** is its script plus a `README.md`. It runs from a fresh clone with one command, on what a Mac already has: Python 3.9+ with the standard library, and bash. A third-party dependency is Stan's call, so ask before adding one.
- **A skill** is installable once `npx skills add stan-voo/tools --list` shows it after the push. The root README carries the install command.
- **A new item gets a row in both tables of the root `README.md`**: the English one and the one under `## Українською`.

## READMEs

The root README promises that each tool's README says what was measured, and on what. `quota-watch/README.md` is the model:

- **Open with scope**: which tools and platforms, whether anything leaves the machine, and exactly which credentials it touches.
- **Every number is measured or labelled.** A real example says it is real. An invented one says "made-up numbers".
- **Credit prior art by name.** Say what was borrowed, and where the other tool is better.
- **`## Limits`** ends with what it was tested on: versions, OS, and for how long.
- **English first, then the Ukrainian translation** under `---` and `## Українською`, with the same sections. Write with the `stan-writing-style` skill and check the Ukrainian with `ukrainian-native-editor`. An English change is done when the Ukrainian says the same thing.

## Publishing

- **Read the staged diff as a stranger would before each commit.** Paths are relative or `~/`-based, example values are placeholders (`<token from BotFather>`), and every name is public. Stan's own paths, private repos, clients, Linear links and secrets belong elsewhere. A secret deleted in a later commit is still published in the history.
- **Personal wiring stays in Stan's private config repo**: a wrapper that maps Stan's own secrets, or a LaunchAgent under Stan's label. A tool reads its settings from the environment or its own env file, so that wiring never has to come in here.
- **Commit messages start with the item's folder**, or the file's name for a root file: `quota-watch: <what changed, in plain words>`, `README: …`.
- **Commit and push in the same breath, staging explicit paths.** Stan's Mac runs the working tree either way, and the push keeps the published repo matching what runs.

## This checkout is live

Stan's Mac runs the tools straight from this working tree. An hourly LaunchAgent execs `quota-watch/quota_watch.py`, so an edit here is in production within the hour.

- **This tree stays on `main`, and every commit leaves it runnable.** Work that spans more than one sitting goes on a branch in a separate git worktree.
- **Test quota-watch against a scratch state dir.** Every command writes to the live history, including `status` and `tick --dry-run`. A real `tick` also marks checkpoints as fired, which cancels the nudge Stan was due to get. Run it as `XDG_STATE_HOME=<scratch dir> python3 quota_watch.py …`. Copy the live `~/.local/state/quota-watch/history.jsonl` into the scratch dir first if the output needs a real pace.

## Reviews

A `SAFETY-REVIEW.md` is an outside audit pinned to the commit it names, and it stays as written. A fix cites the finding it closes in its commit message: `quota-watch: fix review finding 3, …`.
