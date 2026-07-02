#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import email
import imaplib
import logging
import os
import re
import ssl
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = ROOT / ".env"
DEFAULT_TRACKER_FILE = ROOT / "outputs" / "job_application_tracker.csv"
LEGACY_TRACKER_FILE = ROOT / "tracker" / "applications.csv"
DEFAULT_UNMATCHED_FILE = ROOT / "tracker" / "unmatched_rejections.csv"
DEFAULT_LOG_FILE = ROOT / "logs" / "email_check.log"

DEFAULT_IMAP_SERVER = "imap.gmx.com"
DEFAULT_IMAP_PORT = 993
DEFAULT_MAILBOX = "INBOX"
LOOKBACK_HOURS = 24
BODY_SNIPPET_LIMIT = 500

REJECTION_PHRASES = [
    "after careful consideration",
    "unfortunately",
    "unable to move forward",
    "not selected",
    "no longer under consideration",
    "we have decided not to move forward",
    "we have decided not to proceed",
    "we regret to inform you",
    "regret to inform",
    "not moving forward",
    "not proceed",
    "rejection",
    "rejected",
    "absage",
    "leider",
    "nicht weiter",
    "keine positive rueckmeldung",
    "keine positive rückmeldung",
    "nicht beruecksichtigen",
    "nicht berücksichtigen",
    "wir haben uns entschieden, ihre bewerbung",
    "wir haben uns gegen ihre bewerbung entschieden",
    "vielen dank fuer ihre bewerbung",
    "vielen dank für ihre bewerbung",
]

LEGAL_SUFFIXES = {
    "ag",
    "gmbh",
    "kg",
    "ltd",
    "llc",
    "inc",
    "corp",
    "co",
    "company",
    "limited",
    "sarl",
    "bv",
    "se",
}


@dataclass
class EmailRecord:
    uid: str
    from_name: str
    from_email: str
    subject: str
    date_utc: datetime
    body_snippet: str
    rejection_hits: list[str]
    full_text: str
    unseen: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check GMX for rejection emails and update the tracker.")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE), help="Path to .env file.")
    parser.add_argument("--tracker", default=str(DEFAULT_TRACKER_FILE), help="Primary tracker CSV path.")
    parser.add_argument("--legacy-tracker", default=str(LEGACY_TRACKER_FILE), help="Fallback tracker CSV path.")
    parser.add_argument("--unmatched", default=str(DEFAULT_UNMATCHED_FILE), help="CSV path for unmatched rejection emails.")
    parser.add_argument("--log-file", default=str(DEFAULT_LOG_FILE), help="Log file path.")
    parser.add_argument("--mailbox", default=DEFAULT_MAILBOX, help="IMAP mailbox to inspect.")
    parser.add_argument("--imap-server", default=None, help="IMAP server host name.")
    parser.add_argument("--imap-port", type=int, default=None, help="IMAP server port.")
    return parser.parse_args()


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def get_required_env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    raise SystemExit(f"Missing required environment variable. Expected one of: {', '.join(names)}")


def setup_logging(log_file: Path) -> logging.Logger:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("gmx_rejection_checker")
    logger.setLevel(logging.INFO)
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger


def ascii_fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return normalized.encode("ascii", "ignore").decode("ascii")


def normalize_text(text: str) -> str:
    text = ascii_fold(text).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def load_csv_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    if not path.exists():
        return [], []

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = [row for row in reader if row and None not in row]
        return rows, list(reader.fieldnames or [])


def write_csv_rows(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def ensure_tracker_file(tracker_file: Path, legacy_tracker_file: Path, logger: logging.Logger) -> Path:
    if tracker_file.exists():
        return tracker_file
    if legacy_tracker_file.exists():
        rows, fieldnames = load_csv_rows(legacy_tracker_file)
        for extra in ("rejection_date", "email_subject"):
            if extra not in fieldnames:
                fieldnames.append(extra)
        for row in rows:
            row.setdefault("rejection_date", "")
            row.setdefault("email_subject", "")
        write_csv_rows(tracker_file, rows, fieldnames)
        logger.info("Bootstrapped canonical tracker from legacy tracker at %s", legacy_tracker_file)
        return tracker_file
    raise FileNotFoundError(f"Tracker CSV not found at {tracker_file} or {legacy_tracker_file}")


def connect_imap(host: str, port: int, username: str, password: str) -> imaplib.IMAP4_SSL:
    context = ssl.create_default_context()
    client = imaplib.IMAP4_SSL(host=host, port=port, ssl_context=context)
    client.login(username, password)
    return client


def imap_search_uids(client: imaplib.IMAP4_SSL, mailbox: str, cutoff: datetime) -> tuple[set[str], set[str]]:
    client.select(mailbox)
    date_token = cutoff.strftime("%d-%b-%Y")

    unseen_uids: set[str] = set()
    recent_uids: set[str] = set()

    status, data = client.uid("SEARCH", None, "UNSEEN")
    if status == "OK" and data and data[0]:
        unseen_uids = {uid.decode("ascii") for uid in data[0].split()}

    status, data = client.uid("SEARCH", None, "SINCE", date_token)
    if status == "OK" and data and data[0]:
        recent_uids = {uid.decode("ascii") for uid in data[0].split()}

    return unseen_uids, recent_uids


def fetch_message(client: imaplib.IMAP4_SSL, uid: str) -> EmailRecord | None:
    status, data = client.uid("FETCH", uid, "(BODY.PEEK[] FLAGS)")
    if status != "OK" or not data:
        return None

    raw_bytes = None
    flags_blob = b""
    for item in data:
        if isinstance(item, tuple) and item[1]:
            raw_bytes = item[1]
            flags_blob = item[0] or b""
            break

    if raw_bytes is None:
        return None

    message = BytesParser(policy=policy.default).parsebytes(raw_bytes)
    subject = str(message.get("Subject", "")).strip()
    from_name, from_email = parseaddr(str(message.get("From", "")))
    from_name = from_name.strip() or from_email
    from_email = from_email.strip()

    date_utc = parse_message_date(str(message.get("Date", "")))
    if date_utc is None:
        date_utc = datetime.now(timezone.utc)

    full_text = extract_message_text(message)
    body_snippet = build_snippet(full_text)
    combined_for_detection = " ".join([subject, from_name, from_email, body_snippet, full_text[:2000]])
    rejection_hits = detect_rejection_hits(combined_for_detection)
    unseen = b"\\Seen" not in flags_blob

    return EmailRecord(
        uid=uid,
        from_name=from_name,
        from_email=from_email,
        subject=subject,
        date_utc=date_utc,
        body_snippet=body_snippet,
        rejection_hits=rejection_hits,
        full_text=full_text,
        unseen=unseen,
    )


def parse_message_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except Exception:
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def extract_message_text(message: email.message.EmailMessage) -> str:
    parts: list[str] = []

    if message.is_multipart():
        for part in message.walk():
            content_type = part.get_content_type()
            disposition = (part.get_content_disposition() or "").lower()
            if disposition == "attachment":
                continue
            if content_type == "text/plain":
                text = safe_part_text(part)
                if text:
                    parts.append(text)
            elif content_type == "text/html" and not parts:
                text = html_to_text(safe_part_text(part))
                if text:
                    parts.append(text)
    else:
        content_type = message.get_content_type()
        text = safe_part_text(message)
        if content_type == "text/html":
            text = html_to_text(text)
        if text:
            parts.append(text)

    combined = "\n".join(part for part in parts if part)
    combined = unescape(combined)
    combined = re.sub(r"\r\n?", "\n", combined)
    combined = re.sub(r"[ \t]+", " ", combined)
    combined = re.sub(r"\n{3,}", "\n\n", combined)
    return combined.strip()


def safe_part_text(part: email.message.EmailMessage) -> str:
    try:
        content = part.get_content()
    except Exception:
        payload = part.get_payload(decode=True)
        if isinstance(payload, bytes):
            charset = part.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
        if isinstance(payload, str):
            return payload
        return ""
    if isinstance(content, bytes):
        charset = part.get_content_charset() or "utf-8"
        return content.decode(charset, errors="replace")
    return str(content)


def html_to_text(value: str) -> str:
    value = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def build_snippet(text: str, limit: int = BODY_SNIPPET_LIMIT) -> str:
    snippet = re.sub(r"\s+", " ", text).strip()
    return snippet[:limit]


def detect_rejection_hits(text: str) -> list[str]:
    normalized = normalize_text(text)
    hits: list[str] = []
    for phrase in REJECTION_PHRASES:
        phrase_norm = normalize_text(phrase)
        if phrase_norm and phrase_norm in normalized:
            hits.append(phrase)
    return hits


def is_rejection_email(record: EmailRecord) -> bool:
    return bool(record.rejection_hits)


def score_text_match(needle: str, haystack: str) -> float:
    if not needle or not haystack:
        return 0.0
    needle_norm = normalize_text(needle)
    haystack_norm = normalize_text(haystack)
    if not needle_norm or not haystack_norm:
        return 0.0
    if needle_norm in haystack_norm:
        return 1.0
    needle_tokens = needle_norm.split()
    if needle_tokens and all(token in haystack_norm for token in needle_tokens):
        return 0.92
    return SequenceMatcher(None, needle_norm, haystack_norm).ratio()


def simplified_company_aliases(company: str) -> list[str]:
    raw = normalize_text(company)
    aliases = {raw}
    stripped = re.sub(rf"\\b({'|'.join(sorted(LEGAL_SUFFIXES))})\\b", " ", raw)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    if stripped:
        aliases.add(stripped)
    return sorted(aliases, key=len, reverse=True)


def row_match_score(row: dict[str, str], record: EmailRecord) -> tuple[float, str]:
    company = row.get("company", "")
    role = row.get("role_title", "")
    haystack = " ".join(
        [
            record.from_name,
            record.from_email,
            record.subject,
            record.body_snippet,
            record.full_text[:4000],
        ]
    )
    company_score = max((score_text_match(alias, haystack) for alias in simplified_company_aliases(company)), default=0.0)
    role_score = score_text_match(role, f"{record.subject} {record.full_text[:2000]}")
    combined = (company_score * 0.75) + (role_score * 0.25)
    return combined, company if company_score >= 0.35 else ""


def match_tracker_row(rows: list[dict[str, str]], record: EmailRecord) -> tuple[int | None, float, str]:
    best_index: int | None = None
    best_score = 0.0
    best_company = ""
    for index, row in enumerate(rows):
        score, company = row_match_score(row, record)
        if score > best_score:
            best_index = index
            best_score = score
            best_company = company
    if best_score < 0.52:
        return None, best_score, best_company
    return best_index, best_score, best_company


def normalize_date_for_tracker(value: datetime) -> str:
    return value.astimezone(timezone.utc).date().isoformat()


def update_tracker_row(row: dict[str, str], record: EmailRecord) -> dict[str, str]:
    updated = dict(row)
    updated["status"] = "Rejected"
    updated["rejection_date"] = normalize_date_for_tracker(record.date_utc)
    updated["email_subject"] = record.subject
    updated["next_action"] = "No action; rejection recorded."
    return updated


def is_already_rejected(row: dict[str, str]) -> bool:
    return row.get("status", "").strip().lower() == "rejected"


def append_unmatched(
    unmatched_path: Path,
    record: EmailRecord,
    company_guess: str,
    score: float,
) -> None:
    fieldnames = [
        "detected_at_utc",
        "email_date_utc",
        "from_name",
        "from_email",
        "subject",
        "body_snippet",
        "company_guess",
        "match_score",
        "rejection_hits",
        "imap_uid",
        "mailbox_source",
    ]

    row = {
        "detected_at_utc": datetime.now(timezone.utc).isoformat(),
        "email_date_utc": record.date_utc.isoformat(),
        "from_name": record.from_name,
        "from_email": record.from_email,
        "subject": record.subject,
        "body_snippet": record.body_snippet,
        "company_guess": company_guess,
        "match_score": f"{score:.2f}",
        "rejection_hits": "; ".join(record.rejection_hits),
        "imap_uid": record.uid,
        "mailbox_source": "GMX IMAP",
    }

    existing_rows, existing_fields = load_csv_rows(unmatched_path)
    if not existing_fields:
        write_csv_rows(unmatched_path, [row], fieldnames)
        return

    for column in fieldnames:
        if column not in existing_fields:
            existing_fields.append(column)
    existing_rows.append(row)
    write_csv_rows(unmatched_path, existing_rows, existing_fields)


def persist_tracker(tracker_path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    required_columns = ["rejection_date", "email_subject"]
    for column in required_columns:
        if column not in fieldnames:
            fieldnames.append(column)
    for row in rows:
        for column in required_columns:
            row.setdefault(column, "")
    write_csv_rows(tracker_path, rows, fieldnames)


def main() -> int:
    args = parse_args()
    load_env_file(Path(args.env_file))
    logger = setup_logging(Path(args.log_file))

    tracker_path = ensure_tracker_file(Path(args.tracker), Path(args.legacy_tracker), logger)
    unmatched_path = Path(args.unmatched)

    gmx_user = get_required_env("GMX_EMAIL", "GMX_USERNAME", "GMX_USER")
    gmx_password = get_required_env("GMX_PASSWORD", "GMX_IMAP_PASSWORD")
    imap_host = (
        args.imap_server
        or os.environ.get("GMX_IMAP_SERVER")
        or os.environ.get("GMX_IMAP_HOST")
        or DEFAULT_IMAP_SERVER
    )
    if args.imap_port is not None:
        imap_port = args.imap_port
    else:
        imap_port = int(os.environ.get("GMX_IMAP_PORT", str(DEFAULT_IMAP_PORT)))
    mailbox = os.environ.get("GMX_IMAP_MAILBOX", args.mailbox)

    tracker_rows, tracker_fields = load_csv_rows(tracker_path)
    if not tracker_rows:
        logger.info("Tracker is empty at %s", tracker_path)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    logger.info("Starting GMX rejection check for mailbox=%s cutoff=%s", mailbox, cutoff.isoformat())

    client = connect_imap(imap_host, imap_port, gmx_user, gmx_password)
    try:
        unseen_uids, recent_uids = imap_search_uids(client, mailbox, cutoff)
        candidate_uids = sorted(unseen_uids | recent_uids, key=lambda value: int(value))
        logger.info(
            "Search returned %d unread UIDs and %d recent UIDs (%d unique candidates)",
            len(unseen_uids),
            len(recent_uids),
            len(candidate_uids),
        )

        processed = 0
        matched = 0
        unmatched = 0
        skipped = 0

        for uid in candidate_uids:
            record = fetch_message(client, uid)
            if record is None:
                logger.warning("Skipping UID %s because it could not be fetched", uid)
                continue

            is_recent = record.date_utc >= cutoff
            if not (record.unseen or is_recent):
                logger.info(
                    "Skipping UID %s because it is neither unread nor within the last %d hours",
                    uid,
                    LOOKBACK_HOURS,
                )
                skipped += 1
                continue

            processed += 1
            if not is_rejection_email(record):
                logger.info(
                    "UID %s (%s) is not a rejection email",
                    uid,
                    record.subject or "<no subject>",
                )
                continue

            row_index, score, company_guess = match_tracker_row(tracker_rows, record)
            logger.info(
                "UID %s detected as rejection hits=%s match_score=%.2f company_guess=%s",
                uid,
                ",".join(record.rejection_hits),
                score,
                company_guess or "<none>",
            )

            if row_index is not None:
                original_row = tracker_rows[row_index]
                if is_already_rejected(original_row):
                    logger.info(
                        "Skipping UID %s because tracker row %d for company=%s role=%s is already Rejected",
                        uid,
                        row_index + 2,
                        original_row.get("company", ""),
                        original_row.get("role_title", ""),
                    )
                    continue
                tracker_rows[row_index] = update_tracker_row(original_row, record)
                matched += 1
                logger.info(
                    "Updated tracker row %d for company=%s role=%s",
                    row_index + 2,
                    original_row.get("company", ""),
                    original_row.get("role_title", ""),
                )
            else:
                append_unmatched(unmatched_path, record, company_guess=company_guess, score=score)
                unmatched += 1
                logger.info(
                    "Appended unmatched rejection to %s for sender=%s",
                    unmatched_path,
                    record.from_email or record.from_name,
                )

        persist_tracker(tracker_path, tracker_rows, tracker_fields)
        logger.info(
            "Finished GMX rejection check processed=%d matched=%d unmatched=%d skipped=%d",
            processed,
            matched,
            unmatched,
            skipped,
        )
    finally:
        try:
            client.logout()
        except Exception:
            pass
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
