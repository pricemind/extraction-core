from pricemind_extraction.encoding import detect_html_encoding, fix_html_encoding, should_detect_encoding
from pricemind_extraction.extractors.default import DefaultExtractor, IExtractor, strip
from pricemind_extraction.js_transformers import DummyTransformer, ITransformer, MagentoTransformer
from pricemind_extraction.selector import (
    JsSelector,
    PriceSelector,
    SelectCollectionQuery,
    SelectQuery,
    Selector,
    StatusQuery,
    StockStatusQuery,
    UrlQuery,
)


def test_public_api_imports():
    assert DefaultExtractor
    assert DummyTransformer
    assert IExtractor
    assert ITransformer
    assert JsSelector
    assert MagentoTransformer
    assert PriceSelector
    assert SelectCollectionQuery
    assert SelectQuery
    assert Selector
    assert StatusQuery
    assert StockStatusQuery
    assert UrlQuery
    assert detect_html_encoding
    assert fix_html_encoding
    assert should_detect_encoding
    assert strip


def test_selector_accepts_selector_like_positional_input():
    source = Selector(text="<html><body><span>ok</span></body></html>")
    wrapped = Selector(source.selector)

    assert wrapped.select({"type": "css", "query": "span::text"}).get() == "ok"
