# Approved model amendment — 24 October 2026

Approved by the user in this conversation before any new experimental generation or scoring.

- Model A stays gpt-4o-mini-2024-07-18 via OpenAI, temperature 0, max_tokens 220, seed 20261020.
- Model B changes from Qwen 2.5 7B / Llama 3.1 8B to gemma-4-26b-a4b-it via Google AI Studio's free API. Preserve prompt text and generation temperature/output limit; record any unsupported API setting rather than silently changing it.
- The blind judge changes from Claude/Gemini to gpt-5.4-nano via OpenAI, reasoning disabled and temperature 0. This departs from the independent-provider judge requirement: both Model A and the judge are supplied by OpenAI. Report this limitation, lexical disagreement, and the human blind sheet.
- The reason for both substitutions is avoiding minimum provider top-ups while using the user's existing OpenAI credit. The user's stated available balance is USD 0.76. Target maximum experiment spend USD 0.65, reserving USD 0.11 for uncertainty.
- Do not modify the original preregistration, shared system prompt, original 246 responses, or manuscript. The original preregistration commit remains e0bf6d93f8c5447d2e5ff1d782228c8204490867.
- Keep the existing sample, inputs, scoring definitions, paired comparisons, and seeds. The human audit remains pending until the user supplies annotations; automated scores are provisional.
- No original code implementing the main run's "specific closure reason conveyed" endpoint has been located. Do not replace that endpoint silently. Complete the specified FIX_CLAIM analysis and report that endpoint as unavailable until its original implementation or an approved definition is supplied.

## Provider compatibility finding, before Model B outputs

Google's OpenAI-compatible endpoint rejected the original generator's `seed` parameter with HTTP 400 (unknown field). Keep the original generation file unchanged. A provider transport adapter omits only the unsupported seed and throttles Google requests to 30 RPM. Temperature 0, max_tokens 220, system text, user text, and model selection are unchanged. Record requested seed 20261020 and actual API seed null for Model B, including the main rerun. Preserve the failed request in the failure ledger. The original main script is executed unchanged through runpy under this adapter, with a new output path and the approved model argument.

Gemma initially returned three length-terminated completions under its default thinking configuration. These are preserved in attempts_B.jsonl and not treated as complete responses. The provider adapter explicitly disables thinking (reasoning_effort none), preserving the 220-token response limit. This provider setting is recorded for all subsequent Model B requests.

The compatibility endpoint also rejected reasoning_effort none (thinking budget unsupported). The final adapter therefore uses Google's native generateContent transport with thinkingLevel minimal (documented thinking-off setting). It preserves the system and user message texts byte for byte, temperature 0, and maxOutputTokens 220. API seed is omitted and recorded as null. Native requests/responses are retained in google_transport_ledger.jsonl; the untouched historical script receives a normalized completion response. Earlier compatibility failures remain logged.
