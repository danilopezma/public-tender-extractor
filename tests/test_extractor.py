from tender_extractor.extraction import extractor


class FakePage:
    def __init__(self, text):
        self._text = text

    def extract_text(self):
        return self._text


class FakePdf:
    def __init__(self, texts):
        self.pages = [FakePage(t) for t in texts]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def detect(monkeypatch, texts):
    monkeypatch.setattr(extractor.pdfplumber, "open", lambda path: FakePdf(texts))
    return extractor.detect_segments("any.pdf")


LONG = "x" * extractor.SCANNED_TEXT_THRESHOLD
SHORT = "x" * (extractor.SCANNED_TEXT_THRESHOLD - 1)


def test_consecutive_pages_of_same_kind_are_grouped(monkeypatch):
    assert detect(monkeypatch, [LONG, LONG, SHORT, SHORT, SHORT]) == [
        (1, 2, "native"),
        (3, 5, "scanned"),
    ]


def test_threshold_boundary(monkeypatch):
    assert detect(monkeypatch, [LONG, SHORT]) == [(1, 1, "native"), (2, 2, "scanned")]


def test_page_without_text_layer_is_scanned(monkeypatch):
    assert detect(monkeypatch, [LONG, None, LONG]) == [
        (1, 1, "native"),
        (2, 2, "scanned"),
        (3, 3, "native"),
    ]


def test_watermark_only_page_is_scanned(monkeypatch):
    assert detect(monkeypatch, ["1264815374985486836290"]) == [(1, 1, "scanned")]
