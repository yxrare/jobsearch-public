from __future__ import annotations

import csv
import importlib
import argparse
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


checker = importlib.import_module("scripts.gmx_rejection_checker")


def make_email_bytes(subject: str, from_addr: str, body: str, date_str: str) -> bytes:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = from_addr
    message["To"] = "applicant@example.com"
    message["Date"] = date_str
    message.set_content(body)
    return message.as_bytes()


def make_args(**overrides):
    base = {
        "env_file": str(ROOT / ".env"),
        "tracker": "",
        "legacy_tracker": "",
        "unmatched": "",
        "log_file": "",
        "mailbox": "INBOX",
        "imap_server": None,
        "imap_port": None,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


class FakeImapClient:
    def __init__(self, messages: dict[str, tuple[bytes, bytes]]):
        self.messages = messages
        self.selected_mailbox = None
        self.logged_out = False

    def select(self, mailbox: str):
        self.selected_mailbox = mailbox
        return "OK", [b""]

    def uid(self, command: str, *args):
        if command == "SEARCH":
            if args == (None, "UNSEEN"):
                return "OK", [b"1 2"]
            if args == (None, "SINCE", "21-Jun-2026"):
                return "OK", [b"1 2"]
            return "OK", [b""]
        if command == "FETCH":
            uid = str(args[0])
            if uid not in self.messages:
                return "NO", []
            flags_blob, raw_bytes = self.messages[uid]
            return "OK", [(flags_blob, raw_bytes)]
        return "NO", []

    def logout(self):
        self.logged_out = True
        return "BYE", [b""]


class GMXRejectionCheckerTest(unittest.TestCase):
    def test_detect_rejection_hits_handles_english_and_german(self):
        hits = checker.detect_rejection_hits(
            "Unfortunately, after careful consideration, we are unable to move forward. "
            "Leider können wir Ihre Bewerbung nicht berücksichtigen."
        )
        self.assertIn("unfortunately", hits)
        self.assertIn("after careful consideration", hits)
        self.assertIn("unable to move forward", hits)
        self.assertIn("leider", hits)
        self.assertIn("nicht berücksichtigen", hits)

    def test_main_updates_tracker_and_writes_unmatched(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            tracker_path = tmp / "job_application_tracker.csv"
            unmatched_path = tmp / "unmatched_rejections.csv"
            log_path = tmp / "email_check.log"

            tracker_path.write_text(
                "\n".join(
                    [
                        "date_added,company,role_title,location,source,application_url,fit_score,status,materials_ready,submitted_date,follow_up_date,risk_reason,next_action,folder_path",
                        '2026-06-08,example company,"(Junior) Merchandise Planner (all genders)","Hamburg, Germany",SmartRecruiters,,87,Applied,Yes,2026-06-09,2026-06-16,,"Monitor response and follow up if no update by follow-up date.",applications/example',
                    ]
                ),
                encoding="utf-8",
            )

            matched_email = make_email_bytes(
                subject="Update on your application",
                from_addr="example company Recruiting <jobs@example.com>",
                body="Unfortunately, after careful consideration, we are unable to move forward with your application.",
                date_str="Mon, 22 Jun 2026 01:00:00 +0000",
            )
            unmatched_email = make_email_bytes(
                subject="Your application update",
                from_addr="Recruiting Team <recruiting@example.com>",
                body="Leider müssen wir Ihnen mitteilen, dass wir Ihre Bewerbung nicht berücksichtigen können.",
                date_str="Mon, 22 Jun 2026 01:30:00 +0000",
            )
            fake_client = FakeImapClient(
                {
                    "1": (b"FLAGS ()", matched_email),
                    "2": (b"FLAGS ()", unmatched_email),
                }
            )

            env = {
                "GMX_EMAIL": "applicant@example.com",
                "GMX_PASSWORD": "secret",
                "GMX_IMAP_SERVER": "imap.gmx.com",
                "GMX_IMAP_PORT": "993",
            }

            with patch.dict(os.environ, env, clear=False):
                with patch.object(checker, "parse_args", return_value=make_args(
                    tracker=str(tracker_path),
                    unmatched=str(unmatched_path),
                    log_file=str(log_path),
                )):
                    with patch.object(checker, "connect_imap", return_value=fake_client):
                        exit_code = checker.main()

            self.assertEqual(exit_code, 0)
            self.assertTrue(fake_client.logged_out)

            with tracker_path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["status"], "Rejected")
            self.assertEqual(rows[0]["email_subject"], "Update on your application")
            self.assertEqual(rows[0]["next_action"], "No action; rejection recorded.")
            self.assertEqual(rows[0]["rejection_date"], "2026-06-22")

            with unmatched_path.open(newline="", encoding="utf-8") as handle:
                unmatched_rows = list(csv.DictReader(handle))
            self.assertEqual(len(unmatched_rows), 1)
            self.assertEqual(unmatched_rows[0]["from_email"], "recruiting@example.com")
            self.assertEqual(unmatched_rows[0]["mailbox_source"], "GMX IMAP")

    def test_main_skips_already_rejected_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            tracker_path = tmp / "job_application_tracker.csv"
            tracker_path.write_text(
                "\n".join(
                    [
                        "date_added,company,role_title,status,folder_path",
                        "2026-06-12,example company,Analyst (New Grad),Rejected,applications/example-rejected",
                    ]
                ),
                encoding="utf-8",
            )

            matched_email = make_email_bytes(
                subject="We regret to inform you",
                from_addr="example company Recruiting <no-reply@example.com>",
                body="Unfortunately, after careful consideration, we are unable to move forward.",
                date_str="Mon, 22 Jun 2026 01:00:00 +0000",
            )
            fake_client = FakeImapClient({"1": (b"FLAGS ()", matched_email)})

            env = {
                "GMX_EMAIL": "applicant@example.com",
                "GMX_PASSWORD": "secret",
                "GMX_IMAP_SERVER": "imap.gmx.com",
                "GMX_IMAP_PORT": "993",
            }

            with patch.dict(os.environ, env, clear=False):
                with patch.object(checker, "parse_args", return_value=make_args(
                    tracker=str(tracker_path),
                    unmatched=str(tmp / "unmatched_rejections.csv"),
                    log_file=str(tmp / "email_check.log"),
                )):
                    with patch.object(checker, "connect_imap", return_value=fake_client):
                        exit_code = checker.main()

            self.assertEqual(exit_code, 0)
            with tracker_path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["status"], "Rejected")
            self.assertEqual(rows[0].get("email_subject", ""), "")
            self.assertEqual(rows[0].get("rejection_date", ""), "")


if __name__ == "__main__":
    unittest.main()
