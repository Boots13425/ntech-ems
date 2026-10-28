"""Read-only campaign reply diagnostics. Prints identifiers, never credentials or bodies."""
import imaplib
import json
import ssl
import sys
from pathlib import Path
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models import EmailConfiguration, OutboundEmail, CampaignRecipient
from app.services.email_configuration import decrypt


def main():
    with SessionLocal() as db:
        config = db.get(EmailConfiguration, 1)
        sent = list(db.scalars(select(OutboundEmail).where(OutboundEmail.status == 'accepted')))
        known = set(db.scalars(select(CampaignRecipient.email)))
        mailbox = imaplib.IMAP4_SSL(config.imap_host, config.imap_port, ssl_context=ssl.create_default_context(), timeout=15)
        try:
            mailbox.login(decrypt(config.imap_username_encrypted), decrypt(config.imap_password_encrypted))
            status, folders = mailbox.list()
            print('folders', [f.decode(errors='replace') for f in folders if f and (b'\\All' in f or b'INBOX' in f)])
            mailbox.select('INBOX', readonly=True)
            status, uids = mailbox.uid('search', None, 'ALL')
            print('inbox', dict(count=len(uids[0].split()), latest_uid=uids[0].split()[-1].decode() if uids[0] else None))
            for sent_message in sent:
                mid = sent_message.message_id
                status, result = mailbox.uid('search', None, 'OR', 'HEADER', 'In-Reply-To', '"' + mid + '"', 'HEADER', 'References', '"' + mid + '"')
                ids = result[0].split() if status == 'OK' else []
                print('thread', dict(outbound_id=str(sent_message.id), reply_uids=[i.decode() for i in ids]))
                for uid in ids[-10:]:
                    status, parts = mailbox.uid('fetch', uid, '(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID IN-REPLY-TO REFERENCES FROM DATE AUTO-SUBMITTED)])')
                    for part in parts:
                        if isinstance(part, tuple):
                            message = BytesParser(policy=policy.default).parsebytes(part[1])
                            print('reply_headers', json.dumps(dict(uid=uid.decode(), message_id=str(message.get('Message-ID', '')),
                                in_reply_to=str(message.get('In-Reply-To', '')), references=str(message.get('References', '')),
                                known_sender=parseaddr(str(message.get('From', '')))[1].lower() in known, date=str(message.get('Date', '')))))
        finally:
            mailbox.logout()


if __name__ == '__main__':
    main()
