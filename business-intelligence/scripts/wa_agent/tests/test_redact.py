from wa_agent.eval import redact

IOS = """‎[01/10/2026, 09:15:02] Goji Physio: Messages and calls are end-to-end encrypted.
[01/10/2026, 09:15:02] Mei Ling Tan: Hi, is postnatal physio $260? My number is 9123 4567
and email mei.tan@example.com
[01/10/2026, 09:20:11] Goji Physio: Hi Mei Ling! Yes, $260 for 55 min.
[01/10/2026, 09:21:00] Mei Ling Tan: ‎image omitted
[01/10/2026, 09:22:00] Mei Ling Tan: I live at Blk 123 #05-112, 560123. NRIC S1234567D
[01/10/2026, 09:25:00] Goji Physio: Thanks, see you Friday!
"""

ANDROID = """01/10/26, 2:05 pm - Goji Physio: Hello!
01/10/26, 2:06 pm - +65 9876 5432: Do you do home visits in Punggol?
01/10/26, 2:10 pm - Goji Physio: Yes we do, $380 per session.
"""


def test_ios_parse_joins_lines_and_drops_system_noise():
    msgs = redact.parse(IOS)
    assert [m["sender"] for m in msgs] == ["Mei Ling Tan", "Goji Physio", "Mei Ling Tan",
                                           "Mei Ling Tan", "Goji Physio"]
    assert "email mei.tan" in msgs[0]["text"]
    assert msgs[0]["ts"] > 0


def test_android_parse_with_12h_clock():
    msgs = redact.parse(ANDROID)
    assert len(msgs) == 3 and msgs[1]["sender"] == "+65 9876 5432"
    assert msgs[2]["ts"] > msgs[0]["ts"]


def test_redaction_and_cases():
    chats = [redact.parse(IOS), redact.parse(ANDROID)]
    business = redact.detect_business(chats)
    assert business == "Goji Physio"
    all_chats, cases = redact.build(chats, business)
    text = "\n".join(m["text"] for c in all_chats for m in c["messages"])
    for leaked in ("9123 4567", "mei.tan@example.com", "Mei Ling", "S1234567D",
                   "560123", "#05-112", "9876 5432"):
        assert leaked not in text, leaked
    assert "[PHONE]" in text and "[EMAIL]" in text and "[sent a photo]" in text
    assert "$260" in text and "$380" in text  # prices survive
    first = cases[0]
    assert first["history"][-1]["role"] == "customer"
    assert first["goji_reply"].startswith("Hi [NAME]! Yes, $260")
    assert [c["case"] for c in cases] == ["c001-1", "c001-2", "c002-1"]
