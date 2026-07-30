"""
rules.py
Declarative rule definitions and the engine that evaluates them
against incoming Outlook mail items.
"""
from dataclasses import dataclass
from typing import Callable, List
import logging

logger = logging.getLogger("outlook_watcher.rules")


# ---------- Matchers ----------
# A matcher is any callable: (mail_item) -> bool

def subject_contains(text: str, case_sensitive: bool = False) -> Callable:
    needle = text if case_sensitive else text.lower()

    def _match(mail_item) -> bool:
        subject = mail_item.Subject or ""
        haystack = subject if case_sensitive else subject.lower()
        return needle in haystack
    return _match


def subject_equals(text: str, case_sensitive: bool = False) -> Callable:
    def _match(mail_item) -> bool:
        subject = mail_item.Subject or ""
        if case_sensitive:
            return subject == text
        return subject.lower() == text.lower()
    return _match


def sender_is(email_or_name: str) -> Callable:
    target = email_or_name.lower()

    def _match(mail_item) -> bool:
        try:
            sender = (mail_item.SenderEmailAddress or "").lower()
            sender_name = (mail_item.SenderName or "").lower()
        except Exception:
            return False
        return target in sender or target in sender_name
    return _match


def has_attachment() -> Callable:
    def _match(mail_item) -> bool:
        return mail_item.Attachments.Count > 0
    return _match


def all_of(*matchers: Callable) -> Callable:
    return lambda mail_item: all(m(mail_item) for m in matchers)


def any_of(*matchers: Callable) -> Callable:
    return lambda mail_item: any(m(mail_item) for m in matchers)


# ---------- Rule & Engine ----------

@dataclass
class Rule:
    name: str
    matcher: Callable
    actions: List[Callable]  # each is a one-arg callable: (mail_item) -> None
    stop_on_match: bool = True  # if True, no further rules are checked once this matches


class RuleEngine:
    def __init__(self, rules: List[Rule] = None):
        self.rules: List[Rule] = rules or []

    def add_rule(self, rule: Rule):
        self.rules.append(rule)

    def process(self, mail_item):
        subject = getattr(mail_item, "Subject", "<no subject>")
        matched_any = False
        for rule in self.rules:
            try:
                if rule.matcher(mail_item):
                    matched_any = True
                    logger.info("Rule '%s' matched email '%s'", rule.name, subject)
                    for action in rule.actions:
                        try:
                            action(mail_item)
                        except Exception:
                            logger.exception(
                                "Action failed for rule '%s' on email '%s'", rule.name, subject
                            )
                    if rule.stop_on_match:
                        break
            except Exception:
                logger.exception("Matcher failed for rule '%s' on email '%s'", rule.name, subject)
        if not matched_any:
            logger.debug("No rule matched email '%s'", subject)
