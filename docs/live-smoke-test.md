# Live shared-URL smoke test

Issue #1 needs one final class of evidence: a real `chatgpt.com/share/...` capture on macOS, Windows, and Linux.

Use a deliberately public, non-sensitive shared conversation whenever possible. Never commit a private share URL or its transcript to the repository.

## Command

```bash
paic smoke <share-url-or-id>
```

The command performs the normal source load/capture path but prints only non-sensitive evidence:

- operating-system family;
- canonical source kind;
- message count;
- snapshot update time and raw node count when available;
- conversation digest;
- last-user and last-assistant hashes.

It intentionally does **not** print the title, source locator/share URL, or any message text.

## Evidence to post on Issue #1

Paste only the JSON emitted by `paic smoke`, plus the browser family used if browser fallback was required. Do not paste command history containing a private share URL.

A successful run should have `"ok": true`, a non-zero `message_count`, and stable 64-character SHA-256 digest/hash fields.

## Private local validation

If you must test a private share locally, avoid putting the URL directly into a shell-history command. For example, enter it into an environment variable interactively, run `paic smoke` using that variable, then unset it. Only the content-free JSON evidence should be retained.
