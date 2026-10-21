"""Loopback-only SMTP sink for verification; never relays or delivers mail."""
from contextlib import contextmanager
from socketserver import StreamRequestHandler, ThreadingTCPServer
from threading import Thread


class SMTPHandler(StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(10)
        self.wfile.write(b"220 localhost verification SMTP\r\n")
        while line := self.rfile.readline(8192):
            command = line.split(b" ", 1)[0].strip().upper()
            if command in {b"EHLO", b"HELO", b"NOOP", b"MAIL", b"RCPT", b"RSET"}:
                self.wfile.write(b"250 OK\r\n")
            elif command == b"DATA":
                self.wfile.write(b"354 End with a dot\r\n")
                message = []
                while data := self.rfile.readline(8192):
                    if data == b".\r\n":
                        break
                    message.append(data)
                self.server.messages.append(b"".join(message))
                self.wfile.write(b"250 Accepted locally\r\n")
            elif command == b"QUIT":
                self.wfile.write(b"221 Bye\r\n")
                break
            else:
                self.wfile.write(b"502 Unsupported\r\n")


@contextmanager
def smtp_sink():
    with ThreadingTCPServer(("127.0.0.1", 0), SMTPHandler) as server:
        server.daemon_threads = True
        server.messages = []
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join(timeout=5)
