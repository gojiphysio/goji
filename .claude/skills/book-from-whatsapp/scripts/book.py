"""Book one appointment through goji-booking /internal/book.
Usage: python3 -I book.py <booking.json> [--real]
Without --real it is a dry run (every check, nothing written). booking.json:
{"service","physio_focus","variant","date":"YYYY-MM-DD","time":"HH:MM",
 "format":"clinic|home","name","phone":"+65...","email","clinician_id",
 "address","notes","patient_id":"" , "create_patient": true}"""
import json
import subprocess
import sys
import urllib.error
import urllib.request

body = json.load(open(sys.argv[1]))
body["source"] = "whatsapp"
body["dry_run"] = "--real" not in sys.argv
token = subprocess.check_output(
    ["gcloud", "secrets", "versions", "access", "latest",
     "--secret=wa-agent-internal-token", "--project=goji-bi"]).decode().strip()
req = urllib.request.Request(
    "https://booking.gojiphysio.com/internal/book", data=json.dumps(body).encode(),
    headers={"Content-Type": "application/json", "X-Internal-Token": token}, method="POST")
try:
    print(urllib.request.urlopen(req, timeout=60).read().decode())
except urllib.error.HTTPError as e:
    print(e.code, e.read().decode())
    sys.exit(1)
