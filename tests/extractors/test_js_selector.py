import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

import pricemind_extraction
from pricemind_extraction.extractors.default import DefaultExtractor
from pricemind_extraction.selector import JsSelector, Selector

LD_JSON = {"type": "xpath", "query": "//script[@type='application/ld+json']/text()", "ldjson": True}


def extractor_for(mocker: MockerFixture, data: dict) -> DefaultExtractor:
    html = f'<html><head><script type="application/ld+json">{json.dumps(data)}</script></head><body></body></html>'
    return DefaultExtractor(Selector(text=html), mocker.MagicMock())


def test_js_list_of_plain_strings_returns_values(mocker):
    extractor = extractor_for(mocker, {
        "@type": "Product",
        "image": ["https://example.com/a.jpg", "https://example.com/b.jpg"],
    })

    images = extractor.extract_url({"type": "js", "query": "image", "js": LD_JSON}, "https://example.com/")

    assert images == ["https://example.com/a.jpg", "https://example.com/b.jpg"]


def test_js_list_items_still_parse_js_objects():
    selector = JsSelector({"items": ['{"a": 1}', "https://example.com/a.jpg"]})

    values = [item.get() for item in selector.js("items")]

    assert values == [{"a": 1}, "https://example.com/a.jpg"]


def test_js_filter_on_object_does_not_corrupt_cached_json(mocker):
    extractor = extractor_for(mocker, {
        "offers": {
            "a": {"price": 1, "available": True},
            "b": {"price": 2, "available": False},
        },
    })

    available = extractor.extract_str({"type": "js", "query": "offers[?(@.available == true)].price", "js": LD_JSON})
    price_a = extractor.extract_str({"type": "js", "query": "offers.a.price", "js": LD_JSON})

    assert available == "1"
    assert price_a == "1"


def test_js_filter_on_list_is_repeatable(mocker):
    extractor = extractor_for(mocker, {
        "assets": [
            {"type": "primary", "url": "https://example.com/primary.jpg"},
            {"type": "seal", "url": "https://example.com/seal.jpg"},
            {"type": "gallery", "url": "https://example.com/gallery.jpg"},
        ],
    })
    query = {"type": "js", "query": "assets[?(@.type =~ '^(primary|gallery)$')].url", "js": LD_JSON}

    first = extractor.extract_str(query)
    second = extractor.extract_str(query)
    seal = extractor.extract_str({"type": "js", "query": "assets[1].url", "js": LD_JSON})

    assert first == second == ["https://example.com/primary.jpg", "https://example.com/gallery.jpg"]
    assert seal == "https://example.com/seal.jpg"


ALL_STRATEGY_SCRIPT = """
import json, logging
from pricemind_extraction.extractors.default import DefaultExtractor
from pricemind_extraction.selector import Selector, SelectCollectionQuery

html = '<ul id="a"><li>delta</li><li>alpha</li><li>charlie</li></ul><ul id="b"><li>charlie</li><li>bravo</li></ul>'
extractor = DefaultExtractor(Selector(text=html), logging.getLogger("test"))
query = SelectCollectionQuery([
    {"type": "css", "query": "#a li::text"},
    {"type": "css", "query": "#b li::text"},
], strategy="all")
print(json.dumps(extractor.extract_str(query)))
"""


@pytest.mark.parametrize("hash_seed", ["0", "1", "2", "3", "4", "5"])
def test_extract_all_strategy_keeps_source_order_across_processes(hash_seed):
    src = str(Path(pricemind_extraction.__file__).resolve().parent.parent)
    env = {**os.environ, "PYTHONHASHSEED": hash_seed,
           "PYTHONPATH": os.pathsep.join(filter(None, [src, os.environ.get("PYTHONPATH")]))}

    out = subprocess.run([sys.executable, "-c", ALL_STRATEGY_SCRIPT], env=env, capture_output=True, text=True,
                         check=True)

    assert json.loads(out.stdout) == ["delta", "alpha", "charlie", "bravo"]
