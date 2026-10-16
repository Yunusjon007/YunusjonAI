# Validation — 2026-10-16

58 automated checks passed using Node and local Chromium on synthetic fixtures:

- 28 engine checks: unread chats answered on first sight, baselines, duplicate prevention, stale replies, saved send state, uncertain outcomes, cancellation, provider fallback, review mode, Telegram group filtering, answering queued messages before the next network is scanned and retry timing.
- 22 DOM checks: unread markers in chat lists (blue dots, counter badges, skipped groups and archive), opening unread rows, incoming/outgoing messages, editor scope, drafts, changed conversations, media, AI response completion, multi-line prompts and replies in paragraph-based editors, Enter fallback and read receipts.
- 5 dashboard checks: settings, narrow viewport, safe rendering of customer text, protection against simultaneous controllers and background-safe timers.
- 3 end-to-end checks: the unpacked extension runs in Chromium against look-alike Instagram, Telegram and ChatGPT pages served locally. It answers an unread Instagram message in the General folder and an unread Telegram private chat without any chat being opened by hand, leaves read chats and groups alone, and answers a chat queued from the manual check.

## Changes in 1.0.2

- Chats are found from unread markers in each chat list (Instagram Primary and General, Facebook, Telegram) instead of opening every known chat one by one. Only unread chats are opened.
- An unread message is answered the first time it is seen. Previously a newly found chat was only recorded, so its first message was never answered.

## Fixes in 1.0.1

- Replies were never produced: every AI prompt spans several lines, and ChatGPT, Claude and Gemini store each line as a separate paragraph, so the exact text check after typing failed and every provider was put on a 15-minute cooldown. Typed text is now compared word by word, the send button is awaited, and submission is confirmed.
- Multi-line replies sent to a chat were reported as uncertain and blocked the conversation. Sent messages are now confirmed without depending on line breaks.
- A read receipt or an older message loading between queueing and sending made the job stale for good. Only a different latest message now invalidates a reply.
- Queued messages waited until every network had been scanned. They are now answered right after the network where they were found.
- Waits stalled while the dashboard tab was in the background, because Chrome throttles hidden-tab timers. Waits now run on a worker timer.
- Telegram ignored chat switches made through the address, so its chats could not be read. Chats are now opened from the chat list, with a reload as fallback. Groups and channels are skipped.

These tests do not establish compatibility with current live Instagram, Facebook, Telegram, ChatGPT, Claude or Gemini accounts. No live account messages were sent. Installation in a real Chrome profile and real provider flows require user validation. Start in review mode and check the incoming/outgoing preview before enabling automatic replies.

The extension has no API key or extra API billing. Existing website subscriptions and usage limits apply. The dashboard must remain open. Newly discovered chats are baselined, so an already visible first message is skipped until it changes; use the manual prepare-reply button for that message. Only accessible supported text chats are scanned; this is not guaranteed inbox-wide coverage.

## Optional developer tests

Regular installation requires no developer tools. To rerun checks, use Node 22+ and OpenSSL (for the end-to-end checks), enter the tests folder and run:

```sh
npm install
npx playwright install chromium
npm test
```

AIY_CHROMIUM can optionally point to a local Chromium executable. Test pages intercept website requests and do not use real accounts.
