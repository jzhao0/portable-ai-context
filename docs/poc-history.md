# PoC history

The prototype that motivated this repository evolved through a dozen local iterations. The useful lessons were architectural rather than UI-specific:

- complete webpage HTML can contain non-conversation runtime data;
- whitelist extraction is safer than broad parsing followed by redaction;
- shared conversations can represent snapshots, so tail verification matters;
- long projects need hierarchical state extraction rather than one-shot summarization;
- incremental compilation can reuse prior checkpoint notes when the conversation prefix is unchanged;
- extraction and compilation should be decoupled so clean local archives remain useful without an API key.

The public repository intentionally does not include private raw exports or user-specific credentials/configuration.
