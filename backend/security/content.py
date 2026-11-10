"""Text boundaries, local PII redaction and URL confinement."""
import html
from html.parser import HTMLParser
import logging
import re
import traceback
import unicodedata
from urllib.parse import urlsplit
from pathlib import Path

import yaml

EMAIL = re.compile(r'(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b')
CARD_GROUPS = re.compile(r'(?<![\w-])(?:\d{4}[ -]){3}\d{4}(?!\d)')
NUMBER = re.compile(r'(?<![\w])\+?\d(?:[ ().-]*\d){9,18}(?![\w])')
UUID = re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', re.I)
URL = re.compile(r'(?i)(?:https?://|javascript:|data:|file:|ftp:|www\.)[^\s<>"\]）]+')


def redact(text):
    # Preserve canonical machine IDs; they are not phone/card numbers.
    saved = []
    def keep(match):
        saved.append(match.group())
        return f'__INTERNAL_UUID_{len(saved) - 1}__'
    text = UUID.sub(keep, str(text))
    text = EMAIL.sub('[REDACTED_EMAIL]', text)
    def number(match):
        digits = re.sub(r'\D', '', match.group())
        return '[REDACTED_CARD]' if 13 <= len(digits) <= 19 else '[REDACTED_PHONE]'
    text = CARD_GROUPS.sub('[REDACTED_CARD]', text)
    text = NUMBER.sub(number, text)
    for index, value in enumerate(saved):
        text = text.replace(f'__INTERNAL_UUID_{index}__', value)
    return text


def visible(text):
    return ''.join(c for c in unicodedata.normalize('NFKC', html.unescape(str(text))) if (c in '\n\t' or not unicodedata.category(c).startswith('C')) and unicodedata.category(c) not in {'Mn', 'Me', 'Zl', 'Zp'})


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {'script', 'style', 'iframe', 'object'}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag.lower() in {'script', 'style', 'iframe', 'object'}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def sanitize_text(text, limit=600):
    text = visible(text)
    parser = PlainText()
    parser.feed(text)
    text = ''.join(parser.parts)
    # Images are never rendered from retrieved content; links become plain labels.
    text = re.sub(r'!\[[^\]]*\]\([^\n]*?\)', '', text)
    text = re.sub(r'\[([^\]]*)\]\([^\n]*?\)', r'\1', text)
    text = re.sub(r'(?im)^\s*\[[^\]]+\]:\s*\S+.*$', '', text)
    text = URL.sub('', text)
    return redact(text)[:limit]


def safe_url(value):
    if not isinstance(value, str) or visible(value) != value or redact(value) != value:
        return None
    try:
        url = urlsplit(value)
        return value if url.scheme in {'http', 'https'} and url.hostname and not url.username and not url.password else None
    except ValueError:
        return None


def allow_urls(text, allowed):
    return URL.sub(lambda match: match.group() if match.group() in allowed and safe_url(match.group()) else '[link removed]', text)


def clean_tool_result(value):
    if isinstance(value, dict):
        return {key: (safe_url(item) if key == 'url' else sanitize_text(item, 600 if key == 'excerpt' else 2000)
                      if isinstance(item, str) and key in {'excerpt', 'title', 'attribution', 'display_name', 'name', 'message'}
                      else clean_tool_result(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [clean_tool_result(item) for item in value]
    return value


def clean_answer(value, allowed):
    if isinstance(value, str):
        return allow_urls(redact(visible(value)), allowed)
    if isinstance(value, list):
        return [clean_answer(item, allowed) for item in value]
    if isinstance(value, dict):
        return {key: clean_answer(item, allowed) for key, item in value.items()}
    return value


def unsafe_request(text):
    policy = yaml.safe_load((Path(__file__).resolve().parents[2] / 'config/safety.yaml').read_text())
    text = visible(text)
    return any(re.search(pattern, text, re.I) for pattern in policy['refuse_patterns'])


def install_log_redaction():
    factory = logging.getLogRecordFactory()
    if getattr(factory, '_pii_redaction', False):
        return
    def safe_record(*args, **kwargs):
        record = factory(*args, **kwargs)
        # Formatters such as Uvicorn's access logger inspect the original tuple.
        record.msg = redact_values(record.msg)
        record.args = redact_values(record.args)
        if record.exc_info:
            record.exc_text = redact(''.join(traceback.format_exception(*record.exc_info)))
            record.exc_info = None
        return record
    safe_record._pii_redaction = True
    logging.setLogRecordFactory(safe_record)
    original = logging.Logger.makeRecord
    def make_record(self, *args, **kwargs):
        record = original(self, *args, **kwargs)
        # Logger adds structured extras after the record factory returns.
        for name, value in list(record.__dict__.items()):
            record.__dict__[name] = redact_values(value)
        return record
    logging.Logger.makeRecord = make_record
    original_format = logging.Formatter.format
    def format_record(self, record):
        # Also catch PII assembled by interpolation, including numeric arguments.
        return redact(original_format(self, record))
    logging.Formatter.format = format_record


def redact_values(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {key: redact_values(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return type(value)(redact_values(item) for item in value)
    return value
