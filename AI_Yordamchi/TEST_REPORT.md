# Validation — 2026-10-16

42 automated checks passed using Node and local Chromium on synthetic fixtures:

- 23 engine checks: baselines, duplicate prevention, stale replies, saved send state, uncertain outcomes, cancellation, provider fallback and review mode.
- 15 DOM checks: incoming/outgoing messages, editor scope, drafts, changed conversations, media and AI response completion.
- 4 dashboard checks: settings, narrow viewport, safe rendering of customer text and protection against simultaneous controllers.

These tests do not establish compatibility with current live Instagram, Facebook, Telegram, ChatGPT, Claude or Gemini accounts. No live account messages were sent. Installation in a real Chrome profile and real provider flows require user validation. Start in review mode and check the incoming/outgoing preview before enabling automatic replies.

The extension has no API key or extra API billing. Existing website subscriptions and usage limits apply. The dashboard must remain open. Newly discovered chats are baselined, so an already visible first message is skipped until it changes; use the manual prepare-reply button for that message. Only accessible supported text chats are scanned; this is not guaranteed inbox-wide coverage.

## Optional developer tests

Regular installation requires no developer tools. To rerun checks, use Node 22+, enter the tests folder and run:

```sh
npm install
npx playwright install chromium
npm test
```

AIY_CHROMIUM can optionally point to a local Chromium executable. Test pages intercept website requests and do not use real accounts.
