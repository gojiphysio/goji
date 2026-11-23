"""Stand-ins for the Anthropic client and the WhatsApp sender."""
from __future__ import annotations

import json
from types import SimpleNamespace as NS


def usage(i=100, o=50, cr=0, cw=0):
    return NS(input_tokens=i, output_tokens=o, cache_read_input_tokens=cr,
              cache_creation_input_tokens=cw)


def final(reply="Hi! We're open Mon-Sat 8am-8pm.", intent="location_hours", confidence=0.95,
          escalate=False, reason="", note="asks hours", stop="end_turn", holding=""):
    body = json.dumps({"reply": reply, "intent": intent, "confidence": confidence,
                       "escalate": escalate, "escalation_reason": reason, "staff_note": note,
                       "holding_reply": holding})
    return NS(stop_reason=stop, model="served-model", usage=usage(cr=20000),
              content=[NS(type="text", text=body)])


def tool_call(name, inp, tid="tu_1"):
    return NS(stop_reason="tool_use", model="served-model", usage=usage(cw=20000),
              content=[NS(type="tool_use", id=tid, name=name, input=inp)])


class FakeClaude:
    """Returns the queued responses in order; records every request."""

    def __init__(self, *responses):
        self.queue = list(responses)
        self.requests = []
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kw):
        self.requests.append(kw)
        r = self.queue.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class FakeWhatsApp:
    def __init__(self, fail=False):
        self.sent = []
        self.typing = []
        self.fail = fail

    def send_text(self, wa_id, text):
        if self.fail:
            raise RuntimeError("send failed")
        self.sent.append((wa_id, text))
        return f"wamid.out{len(self.sent)}"

    def mark_read_typing(self, msg_id):
        self.typing.append(msg_id)

    media = (b"", "")

    def download_media(self, media_id):
        return self.media
