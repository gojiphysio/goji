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


# --- layout: category folders, zip + unzipped copy -------------------------

def _zip(path, text):
    import zipfile
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("_chat.txt", text)


def test_find_exports_recurses_categories_and_dedupes_unzipped(tmp_path):
    (tmp_path / "regular").mkdir()
    (tmp_path / "sensitive-doctors-referral").mkdir()
    _zip(tmp_path / "regular" / "WhatsApp Chat - A.zip", IOS)
    (tmp_path / "regular" / "WhatsApp Chat - A").mkdir()          # unzipped copy
    (tmp_path / "regular" / "WhatsApp Chat - A" / "_chat.txt").write_text(IOS)
    (tmp_path / "regular" / "WhatsApp Chat - B").mkdir()          # folder only
    (tmp_path / "regular" / "WhatsApp Chat - B" / "_chat.txt").write_text(IOS)
    _zip(tmp_path / "sensitive-doctors-referral" / "WhatsApp Chat - C.zip", IOS)
    (tmp_path / "loose.txt").write_text(ANDROID)                     # top level
    (tmp_path / "__MACOSX").mkdir()
    (tmp_path / "__MACOSX" / "x.txt").write_text("junk")

    found = [(p.relative_to(tmp_path).as_posix(), cat) for p, cat in redact.find_exports(tmp_path)]
    assert sorted(found) == sorted([
        ("loose.txt", ""),
        ("regular/WhatsApp Chat - A.zip", "regular"),
        ("regular/WhatsApp Chat - B/_chat.txt", "regular"),
        ("sensitive-doctors-referral/WhatsApp Chat - C.zip", "sensitive-doctors-referral"),
    ])


def test_build_records_category_and_marks_partner_chats_b2b():
    chats = [redact.parse(IOS), redact.parse(IOS)]
    all_chats, cases = redact.build(chats, "Goji Physio",
                                    ["new-enquiries", "sensitive-doctors-referral"], keep=set())
    assert [(c["category"], c["b2b"]) for c in all_chats] == [
        ("new-enquiries", False), ("sensitive-doctors-referral", True)]
    assert {(c["case"][:4], c["category"], c["b2b"]) for c in cases} == {
        ("c001", "new-enquiries", False), ("c002", "sensitive-doctors-referral", True)}


# --- iPhone details the first parser missed --------------------------------

IOS_GROUP = (
    "[3/11/26, 7:38:48 PM] Family group: ‎~ Jane Doe created group “Family group”\n"
    "[3/11/26, 7:38:49 PM] Family group: ‎~ Jane Doe added you\n"
    "[3/11/26, 7:40:00 PM] ‪+65 9000 0001‬: Hi can I move my slot? ‎<This message was edited>\n"
    "[3/11/26, 7:41:00 PM] Goji Physio: ‎Voice call, ‎Answered on other device\n"
    "[3/11/26, 7:42:00 PM] ‪+65 9000 0001‬: ‎image omitted\n"
    "[3/11/26, 7:43:00 PM] Goji Physio: Sure!\n"
)


def test_ios_system_lines_dropped_edited_kept_bidi_stripped():
    msgs = redact.parse(IOS_GROUP)
    assert [m["sender"] for m in msgs] == ["+65 9000 0001"] * 2 + ["Goji Physio"]
    all_chats, _ = redact.build([msgs], "Goji Physio", keep=set())
    texts = [m["text"] for m in all_chats[0]["messages"]]
    assert texts == ["Hi can I move my slot?", "[sent a photo]", "Sure!"]


# --- names typed in the text, not just the sender's ------------------------

def _redacted(lines: list[tuple[str, str]], **kw) -> str:
    text = "".join(f"[01/10/2026, 09:{i:02d}:00] {who}: {body}\n" for i, (who, body) in enumerate(lines))
    all_chats, _ = redact.build([redact.parse(text)], "Goji Physio", keep={"chris", "kristy"},
                                vocab={"can", "got", "assessment", "looking", "mummy", "baby"}, **kw)
    return "\n".join(m["text"] for m in all_chats[0]["messages"])


def test_names_found_from_greetings_intros_titles_relations_and_fields():
    out = _redacted([
        ("+65 9000 0001", "Hi, Can I book for my son Bertrand?"),
        ("Goji Physio", "Hey Zelphine! Kristy has Friday. Thanks Zelphine Got it"),
        ("+65 9000 0001", "my name is quorra, referred by Dr Obadiah Venn"),
        ("+65 9000 0001", "Full Name: Quorra Ilsabet Venn\nMobile: 9000 0002"),
        ("+65 9000 0001", "Baby details:\nOrlaith Venn\nDOB 08/09/26\nalso baby Tamsin"),
        ("+65 9000 0001", "My partner's number: Fennick 8000 0003"),
        ("Goji Physio", "This is Chris here. Mummy & Baby Assessment is $260. Bertrand and quorra can come."),
    ])
    for leaked in ("Bertrand", "Zelphine", "quorra", "Quorra", "Obadiah", "Venn", "Ilsabet",
                   "Orlaith", "Tamsin", "Fennick", "08/09/26", "9000 0002"):
        assert leaked not in out, leaked
    # staff names and common words after a cue survive
    for kept in ("Can I book", "Kristy has Friday", "Got it", "This is Chris", "Baby Assessment",
                 "Dr [NAME]", "DOB [DOB]", "Mobile: [PHONE]"):
        assert kept in out, kept


def test_two_letter_name_tokens_redacted_but_not_english_words():
    out = _redacted([("~ Ai Wen", "Hi! Is it ok if I come at 9?"),
                     ("Goji Physio", "Hey Ai Wen! Yes it is ok, see you")])
    assert "Ai" not in out and "Wen" not in out
    assert "Is it ok if I come" in out and "Yes it is ok" in out


def test_addresses_numbers_links_and_document_names():
    out = redact.redact(
        "12A Fernvale Road #05-12 Singapore 159475\nBlk 123 Ang Mo Kio\nThe Larkspur Residences\n"
        "Policy 1234567890, ref 55512-3456, slots 1030-1230\n"
        "Jane Doe memo.pdf • 1 page ‎document omitted\n"
        "https://www.gojiphysio.com/book/ and https://clinic.platomedical.com/book/abc123/def "
        "and https://www.instagram.com/p/XYZ/", [])
    for leaked in ("Fernvale", "123 Ang", "Larkspur", "1234567890", "55512-3456", "Jane Doe",
                   "memo.pdf", "abc123", "/p/XYZ"):
        assert leaked not in out, leaked
    assert "[ADDRESS] [UNIT] Singapore [POSTCODE]" in out
    assert "slots 1030-1230" in out          # time ranges survive
    assert "[sent a document]" in out
    assert "https://www.gojiphysio.com/book/" in out
    assert "[link: platomedical.com]" in out and "[link: instagram.com]" in out


def test_extra_names_and_strict_mode_for_partner_chats(tmp_path):
    f = tmp_path / "extra.txt"
    f.write_text("# third parties\nGhazwyn\n\nMa Kuorin\n")
    names = redact.read_extra_names(f)
    assert names == ["Ghazwyn", "Ma Kuorin"]
    out = _redacted([("+65 9000 0001", "Slot for Ghazwyn after her session with Ma Kuorin?"),
                     ("Goji Physio", "Sure!")], extra_names=names)
    assert "Ghazwyn" not in out and "Kuorin" not in out

    text = ("[01/10/2026, 09:00:00] Dr Clinic: Referring Ysolde, knee pain after a fall\n"
            "[01/10/2026, 09:01:00] Goji Physio: Thanks! Kristy will see Ysolde\n")
    chats, _ = redact.build([redact.parse(text)], "Goji Physio", ["doctors-referral"],
                            keep={"kristy"}, strict_vocab={"referring", "knee", "thanks", "will"})
    body = " ".join(m["text"] for m in chats[0]["messages"])
    assert "Ysolde" not in body and "Kristy will see [NAME]" in body
