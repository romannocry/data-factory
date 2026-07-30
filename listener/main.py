"""
main.py
Example wiring: define rules and start listening for new mail.

Run with:  python main.py
Requires:
  - Windows, with the Outlook desktop app installed and a profile configured
  - pip install pywin32
"""
import logging

from listener import start_listening
from rules import Rule, RuleEngine, subject_contains, sender_is, has_attachment, all_of
import actions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Display name or SMTP address of the shared mailbox, exactly as it appears
# in Outlook's folder pane. The mailbox must already be added to your
# Outlook profile (auto-mapped via Exchange permissions, or added manually
# via File -> Account Settings -> ... -> "Open these additional mailboxes").
SHARED_MAILBOX = "Shared Mailbox Name or shared@company.com"
WATCH_FOLDER = "Inbox"  # or "Inbox/Subfolder"


def build_rules() -> RuleEngine:
    engine = RuleEngine()

    # Rule 1: subject contains "xyz" -> save attachments to a folder, mark read
    engine.add_rule(Rule(
        name="xyz_attachments",
        matcher=subject_contains("xyz"),
        actions=[
            lambda mail: actions.move_attachments(mail, dest_folder=r"C:\EmailAttachments\xyz"),
            actions.mark_as_read,
        ],
        stop_on_match=True,
    ))

    # Rule 2: subject contains "invoice" AND has an attachment
    # -> save attachments, then move the email itself into an Outlook folder
    engine.add_rule(Rule(
        name="invoices",
        matcher=all_of(subject_contains("invoice"), has_attachment()),
        actions=[
            lambda mail: actions.move_attachments(mail, dest_folder=r"C:\EmailAttachments\Invoices"),
            lambda mail: actions.move_email_to_folder(mail, folder_path="Processed/Invoices"),
        ],
        stop_on_match=True,
    ))

    # Rule 3: from a specific sender -> just log it (doesn't stop other rules)
    engine.add_rule(Rule(
        name="log_specific_sender",
        matcher=sender_is("someone@example.com"),
        actions=[actions.log_email],
        stop_on_match=False,
    ))

    return engine


if __name__ == "__main__":
    rule_engine = build_rules()
    start_listening(rule_engine, shared_mailbox=SHARED_MAILBOX, folder_path=WATCH_FOLDER)
