"""CV safety checks and field validation."""
import pytest
from werkzeug.datastructures import MultiDict

from careers.conftest import form_data, make_doc, make_docx, make_pdf, make_pdf_with_compressed
from careers.validation import (FileRejected, check_cv, clean_line, sanitise_filename,
                                validate_form)

PHYSIO = {"id": "physiotherapist", "form": "physio", "also_consider_for": ["senior-physiotherapist"]}


# ---- files ----------------------------------------------------------------------

def test_accepts_plain_pdf_docx_doc():
    assert check_cv("cv.pdf", "application/pdf", make_pdf()) == "pdf"
    assert check_cv("CV Final.DOCX", "application/vnd.openxmlformats-officedocument."
                    "wordprocessingml.document", make_docx()) == "docx"
    assert check_cv("cv.doc", "application/msword", make_doc()) == "doc"
    # Some Android browsers send octet-stream; the signature still decides.
    assert check_cv("cv.pdf", "application/octet-stream", make_pdf()) == "pdf"


@pytest.mark.parametrize("name", ["cv.exe", "cv.pdf.exe", "cv.html", "cv", "cv.docm", "cv.svg"])
def test_rejects_unsupported_extensions(name):
    with pytest.raises(FileRejected):
        check_cv(name, "application/pdf", make_pdf())


def test_rejects_signature_mismatch():
    with pytest.raises(FileRejected):  # an HTML page renamed .pdf
        check_cv("cv.pdf", "application/pdf", b"<html><script>alert(1)</script></html>")
    with pytest.raises(FileRejected):  # a PDF renamed .docx
        check_cv("cv.docx", "application/octet-stream", make_pdf())
    with pytest.raises(FileRejected):  # a zip that isn't a Word document
        check_cv("cv.docx", "application/zip", make_docx(content_types="x").replace(
            b"word/document.xml", b"word/notadocum.xml"))


def test_rejects_mime_mismatch():
    with pytest.raises(FileRejected):
        check_cv("cv.pdf", "text/html", make_pdf())


def test_rejects_empty_and_oversized(monkeypatch):
    with pytest.raises(FileRejected):
        check_cv("cv.pdf", "application/pdf", b"")
    big = make_pdf(b"%" + b"x" * (10 * 1024 * 1024))
    with pytest.raises(FileRejected, match="10MB"):
        check_cv("cv.pdf", "application/pdf", big)


@pytest.mark.parametrize("payload", [
    b"<< /OpenAction << /S /JavaScript /JS (app.alert(1)) >> >>",
    b"<< /AA << /O << /S /J#61vaScript /JS (x) >> >> >>",       # hex-escaped name
    b"<< /S /Launch /F (cmd.exe) >>",
    b"<< /Type /EmbeddedFile >>",
])
def test_rejects_active_pdf(payload):
    with pytest.raises(FileRejected):
        check_cv("cv.pdf", "application/pdf", make_pdf(payload))


def test_rejects_javascript_hidden_in_compressed_object_stream():
    with pytest.raises(FileRejected):
        check_cv("cv.pdf", "application/pdf", make_pdf_with_compressed(b"<< /S /JavaScript >>"))


def test_rejects_docx_macros_activex_embeddings_and_remote_templates():
    for parts in ({"word/vbaProject.bin": b"x"}, {"word/activeX/activeX1.xml": b"x"},
                  {"word/embeddings/oleObject1.bin": b"x"}):
        with pytest.raises(FileRejected):
            check_cv("cv.docx", "", make_docx(extra_parts=parts))
    remote = ('<Relationships><Relationship Id="r1" Type="http://schemas.openxmlformats.org/'
              'officeDocument/2006/relationships/attachedTemplate" '
              'Target="https://evil.example/t.dotm" TargetMode="External"/></Relationships>')
    with pytest.raises(FileRejected):
        check_cv("cv.docx", "", make_docx(rels=remote))


def test_rejects_doc_with_macros():
    with pytest.raises(FileRejected):
        check_cv("cv.doc", "application/msword", make_doc(macros=True))


def test_filename_sanitised():
    assert sanitise_filename("../../etc/passwd") == "passwd"
    assert sanitise_filename("C:\\Users\\x\\My CV<script>.pdf") == "My CV_script_.pdf"
    assert sanitise_filename("Résumé – Jane.pdf") == "Resume Jane.pdf"
    assert sanitise_filename("") == "cv"


# ---- fields ----------------------------------------------------------------------

def _v(**over):
    return validate_form(MultiDict(form_data(**over)), PHYSIO, general=False)


def test_valid_full_time_application():
    r = _v()
    assert r.errors == {}
    assert r.data["employment"] == "Full-time"
    assert r.data["days_per_week"] == ""
    assert r.data["years_experience"] == 4


def test_part_time_requires_days_but_never_rejects_below_minimum():
    assert "days_per_week" in _v(employment="part-time").errors
    r = _v(employment="part-time", days_per_week="2")   # below the 3-day minimum
    assert r.errors == {} and r.data["days_per_week"] == "2"
    assert _v(employment="either", days_per_week="4").errors == {}


@pytest.mark.parametrize("field", ["full_name", "email", "phone", "start_availability",
                                   "intro", "privacy_ack", "employment", "years_experience",
                                   "ahpc_status", "clinical_experience"])
def test_missing_required_fields(field):
    assert field in _v(**{field: None}).errors


@pytest.mark.parametrize("email", ["not-an-email", "a@b", "x@y.c", "a b@c.com",
                                   "victim@example.com\r\nBcc: spam@example.com"])
def test_invalid_email(email):
    assert "email" in _v(email=email).errors


@pytest.mark.parametrize("phone", ["91234567", "+65", "+65 abc 1234", "+1234567890123456"])
def test_invalid_phone(phone):
    assert "phone" in _v(phone=phone).errors


def test_options_must_come_from_the_lists():
    r = _v(ahpc_status="Totally registered", heard_about="Spam site")
    assert "ahpc_status" in r.errors and r.data["heard_about"] == ""


def test_linkedin_must_be_http_url():
    assert "linkedin" in _v(linkedin="javascript:alert(1)").errors
    assert _v(linkedin="https://www.linkedin.com/in/example").errors == {}


def test_general_interest_skips_physio_questions_and_needs_an_area():
    form = MultiDict(form_data(role="general", ahpc_status=None, clinical_experience=None))
    r = validate_form(form, None, general=True)
    assert r.errors == {"interest_area": "Choose the kind of role you're interested in."}
    form = MultiDict(form_data(role="general", interest_area="Pilates instruction"))
    r = validate_form(form, None, general=True)
    assert r.errors == {} and r.data["ahpc_status"] == ""


def test_control_characters_and_newlines_stripped_from_single_line_fields():
    assert clean_line("Jane\r\nBcc: x@y.com\u202e", 100) == "Jane Bcc: x@y.com"
    assert _v(full_name="Jane\nDoe").data["full_name"] == "Jane Doe"
