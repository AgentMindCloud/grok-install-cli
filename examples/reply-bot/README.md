# reply-bot

An X mention-reply bot with mandatory human approval before anything is posted.

```bash
export XAI_API_KEY=...
export X_API_KEY=...
export X_API_SECRET=...
grok-install scan examples/reply-bot
grok-install run examples/reply-bot --prompt "Check for mentions to reply to."
```

Every call to `reply_to_mention` opens a panel asking for approval.
