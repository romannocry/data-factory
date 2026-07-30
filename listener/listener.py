"""
listener.py
Binds to a folder's Items collection (e.g. the Inbox of a shared mailbox)
and listens for newly-added mail items, dispatching each to a RuleEngine.

Shared mailboxes don't fire OnNewMailEx (that event only covers the
signed-in user's own default Inbox), so this uses the more general
Items.ItemAdd event, which works for any folder you can reach via
Namespace.Folders — including shared/other-user mailboxes that have been
added to the Outlook profile.
"""
import logging
import time
import pythoncom
import win32com.client

logger = logging.getLogger("outlook_watcher.listener")

OL_MAIL_ITEM = 43  # olMail — Class value for a normal mail item


def _resolve_watch_folder(namespace, shared_mailbox: str = None, folder_path: str = "Inbox"):
    """
    shared_mailbox: display name or SMTP address of the shared mailbox as it
        appears in Outlook's folder pane (must already be added to the
        profile — auto-mapped via Exchange permissions, or added manually
        via Account Settings -> "Open these additional mailboxes").
        Pass None to watch a folder in your own primary mailbox instead.
    folder_path: path under that mailbox's root, e.g. "Inbox" or
        "Inbox/Subfolder".
    """
    if shared_mailbox:
        root = namespace.Folders[shared_mailbox]
    else:
        root = namespace.GetDefaultFolder(6).Parent  # own mailbox root

    current = root
    for part in [p for p in folder_path.split("/") if p]:
        current = current.Folders[part]
    return current


def _make_handler_class(rule_engine):
    """
    win32com.client.DispatchWithEvents instantiates the handler class itself,
    so the rule_engine is injected as a class attribute via this factory.
    """

    class ItemsEventHandler:
        _rule_engine = rule_engine

        def OnItemAdd(self, item):
            # ItemAdd fires for any item type added to the folder (mail,
            # meeting requests, receipts, etc.) - filter to real mail items.
            try:
                if item.Class != OL_MAIL_ITEM:
                    return
            except Exception:
                return
            try:
                self._rule_engine.process(item)
            except Exception:
                logger.exception("Error processing mail item")

    return ItemsEventHandler


def start_listening(rule_engine, shared_mailbox: str = None, folder_path: str = "Inbox",
                     pump_interval_ms: int = 250):
    """
    Blocking call. Binds to the given folder and pumps the Windows message
    loop so COM events (ItemAdd) actually get delivered. Ctrl+C to stop.
    """
    pythoncom.CoInitialize()
    outlook = win32com.client.Dispatch("Outlook.Application")
    namespace = outlook.GetNamespace("MAPI")

    folder = _resolve_watch_folder(namespace, shared_mailbox, folder_path)
    handler_class = _make_handler_class(rule_engine)
    # Keep a reference to `items` alive for the life of the loop - if it gets
    # garbage collected, the event hookup is dropped.
    items = win32com.client.DispatchWithEvents(folder.Items, handler_class)

    logger.info("Watching folder '%s'%s. (Ctrl+C to stop)",
                folder.FolderPath,
                f" in mailbox '{shared_mailbox}'" if shared_mailbox else "")

    try:
        while True:
            pythoncom.PumpWaitingMessages()
            time.sleep(pump_interval_ms / 1000)
    except KeyboardInterrupt:
        logger.info("Stopped listening (Ctrl+C).")
    finally:
        pythoncom.CoUninitialize()
