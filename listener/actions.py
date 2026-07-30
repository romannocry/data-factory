"""
actions.py
Action functions that operate on an Outlook MailItem (win32com COM object).
Each action takes (mail_item, ...) and returns None (or a result, for move_attachments).
"""
import os
import logging

logger = logging.getLogger("outlook_watcher.actions")


def move_attachments(mail_item, dest_folder: str, delete_from_email: bool = False):
    """Save all attachments of the mail to dest_folder on disk."""
    os.makedirs(dest_folder, exist_ok=True)
    attachments = mail_item.Attachments
    count = attachments.Count
    saved = []
    # Outlook collections are 1-indexed; iterate back-to-front so deleting
    # items while looping doesn't shift the remaining indices.
    for i in range(count, 0, -1):
        attachment = attachments.Item(i)
        filename = attachment.FileName
        dest_path = _unique_path(os.path.join(dest_folder, filename))
        attachment.SaveAsFile(dest_path)
        saved.append(dest_path)
        logger.info("Saved attachment '%s' -> '%s'", filename, dest_path)
        if delete_from_email:
            attachment.Delete()
    if delete_from_email and saved:
        mail_item.Save()
    return saved


def _unique_path(path: str) -> str:
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 1
    while os.path.exists(f"{base}_{i}{ext}"):
        i += 1
    return f"{base}_{i}{ext}"


def move_email_to_folder(mail_item, folder_path: str):
    """
    Move the email into another Outlook folder, resolved relative to the
    root of whichever mailbox/store the email currently lives in. This
    makes it work correctly for shared mailboxes too (not just your own
    primary mailbox) - it never assumes "your" Inbox as the anchor.

    folder_path example: "Processed" or "Processed/Invoices".
    """
    store = mail_item.Parent.Store  # the store (mailbox) this item lives in
    root = store.GetRootFolder()
    target_folder = _resolve_folder(root, folder_path)
    mail_item.Move(target_folder)
    logger.info("Moved email '%s' -> folder '%s'", mail_item.Subject, folder_path)


def _resolve_folder(root_folder, folder_path: str):
    current = root_folder
    for part in [p for p in folder_path.split("/") if p]:
        current = current.Folders[part]
    return current


def mark_as_read(mail_item):
    mail_item.UnRead = False
    mail_item.Save()


def forward_email(mail_item, to: str, note: str = ""):
    fwd = mail_item.Forward()
    fwd.To = to
    if note:
        fwd.Body = f"{note}\n\n{fwd.Body}"
    fwd.Send()
    logger.info("Forwarded email '%s' to %s", mail_item.Subject, to)


def log_email(mail_item):
    logger.info("Email received: '%s' from %s", mail_item.Subject, mail_item.SenderName)
