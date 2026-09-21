# quota-watch safety review

Audited by Astra. Reviewed 21 September 2026: [stan-voo/tools, commit ab24c173018d20ffb7bcd87452e96463fa5dff23](https://github.com/stan-voo/tools/tree/ab24c173018d20ffb7bcd87452e96463fa5dff23/quota-watch).

No critical or high-severity security issue was demonstrated. I found no deliberate credential exfiltration, hidden telemetry, destructive account operation, or downloaded executable payload in the reviewed source. The implementation is small and inspectable. Its principal defects are operational: it can hang, advise work from stale readings, suppress failed notifications, and mix account contexts. Fix those before depending on unattended monitoring.

Scope: all three quota-watch files, static inspection, Python/shell syntax checks, and isolated reproductions using fake readings, fake subprocesses, and mocked delivery. No real provider queries, credential-file inspection, notifications, or LaunchAgent installation were performed. The provider CLIs themselves were not audited, and future commits are outside this review.

## Findings

### 1. P2: Codex I/O can bypass the timeout or miss a response

[quota_watch.py:244–249](https://github.com/stan-voo/tools/blob/ab24c173018d20ffb7bcd87452e96463fa5dff23/quota-watch/quota_watch.py#L244-L249)

`select()` establishes that some bytes are readable; it does not establish that a complete line exists. The subsequent blocking `readline()` can wait indefinitely for a newline, bypassing the enclosing deadline. A second problem is combining descriptor readiness with a buffered text reader: the first `readline()` can buffer a second complete response, leaving `select()` waiting for new kernel bytes even though the needed response is already in Python's buffer.

Reproduced with a fake Codex executable: a 2-second deadline returned after 3.496 seconds when the rest of a partial line arrived. In a separate case, two complete responses written together caused the second response to be missed and the function to return `(None, None)`. A permanently incomplete line would keep the hourly job stuck; missed replies push it into the potentially stale log fallback.

Fix: use nonblocking byte reads with an explicit newline buffer and monotonic deadline, or another transport implementation that bounds the entire exchange. Kill and reap the process and close its pipes on every exit.

### 2. P2: Stale readings can recommend starting heavy work

[quota_watch.py:737–743](https://github.com/stan-voo/tools/blob/ab24c173018d20ffb7bcd87452e96463fa5dff23/quota-watch/quota_watch.py#L737-L743), [message formatting:750–759](https://github.com/stan-voo/tools/blob/ab24c173018d20ffb7bcd87452e96463fa5dff23/quota-watch/quota_watch.py#L750-L759)

Window nudges check reset time and recorded utilization, but not the age of either the session or weekly reading. The window message also omits the stale-data warning that the status and weekly message paths include.

Reproduced using four-hour-old readings and a window resetting in 30 minutes. The message claimed “90% unused” and recommended starting heavy work, although current usage was unknown. This matters when refresh fails or usage occurs on another machine.

Fix: require suitably fresh readings for every limit used in an actionable nudge. Display an unavailable/stale state when that requirement fails.

### 3. P2: Failed notifications are marked as delivered

[quota_watch.py:846–851](https://github.com/stan-voo/tools/blob/ab24c173018d20ffb7bcd87452e96463fa5dff23/quota-watch/quota_watch.py#L846-L851), [macOS fallback:782–788](https://github.com/stan-voo/tools/blob/ab24c173018d20ffb7bcd87452e96463fa5dff23/quota-watch/quota_watch.py#L782-L788)

After a Telegram error, `mac_notify()` ignores the `osascript` exit code. The tick still writes the checkpoint to `fired.json`, preventing a later retry for that checkpoint.

Reproduced with Telegram returning `URLError` and the macOS subprocess returning exit code 1: two consecutive ticks made only one delivery attempt, and checkpoints `[24, 48, 96]` were persisted despite both delivery paths failing.

Fix: return an explicit delivery result, bound the fallback subprocess runtime, and mark a checkpoint fired only after a successful delivery attempt. Retry failed attempts with a bounded policy.

### 4. P2: Env-file account selectors do not reach the provider CLIs

[configuration paths:82–95](https://github.com/stan-voo/tools/blob/ab24c173018d20ffb7bcd87452e96463fa5dff23/quota-watch/quota_watch.py#L82-L95), [Claude subprocess:191–194](https://github.com/stan-voo/tools/blob/ab24c173018d20ffb7bcd87452e96463fa5dff23/quota-watch/quota_watch.py#L191-L194), [Codex subprocess:234–235](https://github.com/stan-voo/tools/blob/ab24c173018d20ffb7bcd87452e96463fa5dff23/quota-watch/quota_watch.py#L234-L235)

Values such as `CODEX_HOME` and `CLAUDE_CONFIG_DIR` loaded from the settings file affect quota-watch's file paths, but subprocesses inherit only the actual process environment. A file-selected Codex profile can therefore coexist with a live query against the default account; Claude can refresh the default cache while quota-watch reads a different cache. Results can be attributed to the wrong account and sent to the configured Telegram chat.

An isolated mocked reproduction confirmed the custom parent paths and missing child selectors. This is conditional on configuring those selectors in the env file; ordinary exported selectors are inherited.

Fix: explicitly forward supported provider/account selectors to each child. Do not pass all of `CONFIG`: that would also expose the Telegram token loaded from the settings file to the provider processes.

### 5. P2: An invalid generated plist can leave an existing installation stopped

[install.sh:29–43](https://github.com/stan-voo/tools/blob/ab24c173018d20ffb7bcd87452e96463fa5dff23/quota-watch/install.sh#L29-L43), [replacement sequence:59–63](https://github.com/stan-voo/tools/blob/ab24c173018d20ffb7bcd87452e96463fa5dff23/quota-watch/install.sh#L59-L63)

Paths and labels are interpolated into XML without escaping. A checkout named `work & tools` produced invalid XML in an isolated `--print` test. An actual reinstall would unload the existing agent before writing and validating that invalid replacement, leaving monitoring stopped.

Fix: serialize the plist with an XML/plist library, validate a temporary file first, then replace and reload the agent. Preserve a recoverable previous plist if loading fails.

## Security and privacy boundaries

- The only direct HTTP destination in quota-watch is the fixed Telegram HTTPS `sendMessage` endpoint. Its payload is the configured chat ID, formatted usage/reset/pace information, and notification settings. Token-bearing exception URLs are deliberately excluded from logs. Provider CLIs make their own authenticated requests.
- The Python script does not explicitly open provider auth files. It nevertheless starts authenticated CLIs that retain their normal account access. This review does not establish that those subprocesses can never consume quota or perform startup side effects across versions/configurations.
- The parser loads the entire Claude configuration JSON before selecting `cachedUsageUtilization`. Backfill/fallback scans complete Codex rollout files line by line. It retains selected usage fields, not raw conversation/configuration content. The README's “no credentials” wording should describe this boundary precisely rather than imply strong process isolation.
- The env file is parsed as text, with no shell evaluation. Subprocesses use argument arrays. There are no third-party Python dependencies, root installation steps, account resets, purchases, or model-work dispatch requests in this source.
- Under umask `022`, isolated tests produced a `0755` state directory and `0644` history/fired files. Other local users may read usage timestamps and percentages if ancestor permissions allow. This is a P3 privacy hardening issue, not a demonstrated credential leak: use a `0700` state directory and `0600` files. The README already recommends `0600` for the Telegram configuration file.
- Claude refresh keeps project settings enabled. Explicitly disabling ordinary hooks would narrow startup side effects; managed hooks are a separate trust boundary. The fixed per-user working directory reduces exposure, and no external attacker-controlled hook path was demonstrated. See [Claude hook trust documentation](https://code.claude.com/docs/en/hooks#workspace-trust).
- `tick --dry-run` previews notifications, but still gathers readings, refreshes Claude when needed, and writes history. It is not an offline or side-effect-free inspection mode.

## Verification evidence

- Full source inspection at the pinned commit; original checkout remained unmodified.
- `ast.parse` passed for Python; `bash -n` passed for the installer.
- Two fake-process I/O reproductions passed.
- Stale-window recommendation and failed-delivery checkpoint reproductions passed.
- Env-file selector mismatch reproduced with mocked subprocesses.
- Installer XML failure and state-file permissions reproduced in temporary directories.

Temporary reproduction files (kept on the reviewer's machine, not published): Codex I/O harness, notification harness, notification output, invalid rendered plist.
