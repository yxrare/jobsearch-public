# Job Search Automation Toolkit

A privacy-conscious toolkit for managing a local job-search workflow. The public version includes generic automation code, tests, and reusable writing templates only.

## What is included

- `scripts/gmx_rejection_checker.py` - IMAP-based rejection email detector and CSV tracker updater.
- `tests/test_gmx_rejection_checker.py` - anonymized unit tests.
- `templates/` - generic resume and cover-letter tailoring templates.

## What is intentionally excluded

This public repository does not include application materials, resumes, cover letters, PDFs, tracker exports, logs, email credentials, personal documents, or company-specific application records.

## Environment

Create a local `.env` file, which must never be committed:

```bash
GMX_EMAIL=applicant@example.com
GMX_PASSWORD=your-imap-password
GMX_IMAP_SERVER=imap.gmx.com
GMX_IMAP_PORT=993
GMX_IMAP_MAILBOX=INBOX
```

## Run

```bash
python3 scripts/gmx_rejection_checker.py
```

## Test

```bash
python3 -m unittest tests/test_gmx_rejection_checker.py
```

## Privacy Notes

Keep real job applications, generated PDFs, raw tracker files, mailbox logs, `.env`, and personal profile notes in a private repository or local-only folder. If private data has ever been committed to a repository, do not make that repository public; create a clean repository with fresh history instead.
