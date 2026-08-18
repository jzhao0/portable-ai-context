# Privacy model

## 1. Runtime metadata

Web applications may embed account, session, bootstrap, telemetry, experimentation, and authorization structures next to visible conversation data. Those structures are not conversation history.

Adapters must prefer allowlisting conversation fields. The ChatGPT HTML adapter intentionally ignores `script#client-bootstrap` and only resolves the share conversation stream required to recover message content.

## 2. Conversation-body secrets

A user may intentionally or accidentally type credentials into a chat. That text *is* conversation content, so silently deleting it could change project history.

The default policy is therefore:

- detect suspicious secret patterns;
- report only category/count;
- never print the matched value;
- do not redact unless an explicit future redaction mode is requested.

## 3. Compiler API boundary

If an external compiler backend is used, canonical conversation chunks are sent to that provider. Extraction, inspection, verification, and `.aicb` creation do not require a model API.
