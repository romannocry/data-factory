# Outlook Watcher

A small Python app that listens for new emails arriving in a **shared
Outlook mailbox** (via COM automation, using `pywin32`) and runs them
through a configurable rule engine — e.g. "if subject contains 'xyz', save
attachments to X".

## How it works

- **`listener.py`** binds to the target folder's `Items` collection (e.g.
  the Inbox of the shared mailbox) with `win32com.client.DispatchWithEvents`
  and handles the `OnItemAdd` event, which fires whenever a new item lands
  in that folder. It pumps the Windows message loop (required for COM
  events to fire) in a loop you can interrupt with Ctrl+C.
  - Note: shared mailboxes don't fire Outlook's `OnNewMailEx` event — that
    one only covers the signed-in user's own default Inbox. `ItemAdd` on
    the folder itself is the correct, general-purpose hook, and it works
    the same way whether the folder is your own or a shared mailbox's.
- **`rules.py`** defines a `Rule` (name, matcher, list of actions,
  `stop_on_match`) and a `RuleEngine` that evaluates rules in order against
  each incoming `MailItem`.
- **`actions.py`** has reusable actions: save attachments to disk, move the
  email to another Outlook folder (resolved relative to whichever mailbox
  the email lives in, so it's shared-mailbox-safe), mark as read, forward,
  log.
- **`main.py`** wires up example rules and points the listener at the
  shared mailbox.

## Setup

1. **Windows only**, with the Outlook desktop app installed and signed in.
2. **The shared mailbox must already be added to your Outlook profile** —
   either auto-mapped (if you have Full Access permission on the shared
   mailbox via Exchange, Outlook usually adds it to the folder pane
   automatically), or added manually via *File → Account Settings →
   Account Settings → Email tab → Change → More Settings → Advanced →
   "Add" (shared mailbox name)*. If you don't see it in Outlook's folder
   pane, the script won't see it either.
3. `pip install -r requirements.txt`
4. In `main.py`, set `SHARED_MAILBOX` to the exact display name (or SMTP
   address) as it appears in Outlook's folder pane, and edit the rules.
5. `python main.py`

Leave the process running — it's a blocking loop that reacts to events as
they arrive. Run it as a background process / scheduled task / Windows
service if you want it always-on.

## Writing rules

```python
from rules import Rule, subject_contains, sender_is, has_attachment, all_of
import actions

Rule(
    name="xyz_attachments",
    matcher=subject_contains("xyz"),          # or sender_is(...), has_attachment(), all_of(...), any_of(...)
    actions=[
        lambda mail: actions.move_attachments(mail, dest_folder=r"C:\EmailAttachments\xyz"),
        actions.mark_as_read,
    ],
    stop_on_match=True,   # stop checking further rules once this one matches
)
```

Matchers available out of the box: `subject_contains`, `subject_equals`,
`sender_is`, `has_attachment`, `all_of(...)`, `any_of(...)`. They're just
`(mail_item) -> bool` callables, so writing a custom one is a two-line
function.

Actions available out of the box: `move_attachments`, `move_email_to_folder`,
`mark_as_read`, `forward_email`, `log_email`. Same idea — an action is just
`(mail_item) -> None`.

## Watching a specific subfolder

Change `WATCH_FOLDER` in `main.py`, e.g. `"Inbox/Vendors"` to watch a
subfolder instead of the top-level Inbox of the shared mailbox.

## Caveats / things to know

- **Permissions**: your Windows-logged-in account needs at least "Full
  Access" (or equivalent read access) permission on the shared mailbox for
  any of this to work — this drives the actual Outlook desktop app, it
  doesn't do its own authentication.
- **This app must run on the same Windows session** as the signed-in
  Outlook profile that has the shared mailbox added — it's desktop COM
  automation, not a headless/server-side service. If you eventually need
  this to run unattended on a server without a logged-in user, that's a
  different architecture (Microsoft Graph API with an app registration,
  which is a bigger but more "production" setup — happy to help with that
  if it becomes a requirement).
- **`mail_item.Move(...)`** on a mail that's about to be re-processed can
  occasionally race with Outlook's own indexing; if you see intermittent
  COM errors on rapid-fire moves, add a short `time.sleep(0.2)` before
  `Move`.
- **`item.Class != 43` filter**: `ItemAdd` fires for anything added to the
  folder, not just mail (meeting requests, read receipts, etc.) — the
  listener already filters to `olMail` (43) before handing items to the
  rule engine.
