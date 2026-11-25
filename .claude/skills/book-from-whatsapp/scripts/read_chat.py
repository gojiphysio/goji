# /// script
# dependencies = ["google-cloud-firestore"]
# ///
"""Print WhatsApp chat transcripts from Firestore (wa_chats) that match a
name, number or word. Usage: uv run read_chat.py <query> [--all]
Shows the last 40 lines per chat unless --all. Transcripts keep 30 days."""
import datetime
import sys

from google.cloud import firestore

SGT = datetime.timezone(datetime.timedelta(hours=8))
q = sys.argv[1].lower().replace("+", "").replace(" ", "")
show_all = "--all" in sys.argv
found = 0
for snap in firestore.Client(project="goji-bi").collection("wa_chats").stream():
    d = snap.to_dict() or {}
    hist = d.get("history") or []
    hay = " ".join([snap.id, str(d.get("name", ""))] + [str(h.get("text", "")) for h in hist]).lower()
    if q not in hay and q not in hay.replace(" ", ""):
        continue
    found += 1
    print(f"===== wa_id {snap.id} | name {d.get('name')!r} | mode {d.get('mode')} "
          f"({d.get('mode_reason')}) | patient {d.get('patient')} | booked {d.get('booked') or '-'}")
    for h in (hist if show_all else hist[-40:]):
        t = datetime.datetime.fromtimestamp(h.get("ts", 0), SGT).strftime("%a %d %b %H:%M")
        print(f"[{t}] {h.get('role')}: {h.get('text')}")
print(f"\n{found} chat(s) matched {sys.argv[1]!r}")
