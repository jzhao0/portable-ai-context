# Test fixtures

`claude_conversation.synthetic.json` is fully synthetic and was created for Portable AI Context adapter tests. It contains no real Claude account, conversation, session, organization, attachment, or user data.

`gemini_my_activity.synthetic.json` is fully synthetic and models only the narrow Google My Activity / Gemini Apps JSON subset documented by the alpha adapter. It contains no real Google account, Gemini conversation, location, attachment, session, authorization, or user data.

`aicb_0_1_alpha_golden.aicb.b64` is a base64 representation of one fixed synthetic historical `.aicb` `0.1-alpha` ZIP specimen. It exists to prove that future readers still load committed historical bytes rather than only round-tripping bundles made by the current writer. Its decoded SHA256 is pinned in `tests/test_aicb_compatibility_floor.py`. The specimen contains only synthetic title/message/source values and no provider account data, private path, URL, token, credential, or real conversation content.

`canonical_role_text_golden.jsonl` is a fixed synthetic historical specimen of PAIC's narrow canonical role/text stream. Its raw file SHA256 and canonical conversation digest are pinned in `tests/test_canonical_stream_compatibility_floor.py`. Tests load the committed JSONL directly rather than regenerating it through the current exporter. It contains only synthetic user/assistant text and no provider/account/runtime metadata.
