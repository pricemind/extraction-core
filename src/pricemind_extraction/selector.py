import re
from typing import TypedDict, Any, Union, Optional

import hjson
import jmespath
from chompjs import chompjs
from parsel import Selector as ParselSelector, SelectorList
from jsonpath_ng.ext import parse

from pricemind_extraction.js_transformers import DummyTransformer, ITransformer, MagentoTransformer
from pricemind_extraction.encoding import detect_html_encoding, fix_html_encoding, should_detect_encoding


class RegexReplace(TypedDict):
    regex: str
    replace: str


class SelectQuery(TypedDict):
    type: str
    query: str
    regex: str
    kind: Optional[str]
    js: Union['SelectQuery', None]
    scope: Union[str, None]
    regex_replace: Union[RegexReplace, None]
    default: Union[str, None]

class UrlQuery(SelectQuery):
    encode_path: Optional[bool]


class SelectCollectionQuery(object):
    strategy: Union[str, None]
    selectors: list[SelectQuery]
    options: Union[dict, None]
    kind: Optional[str]

    def __init__(self, selectors: list[SelectQuery], strategy: Union[str, dict, None] = None,
                 options: Union[dict, None] = None, kind: Optional[str] = None):
        self.strategy = strategy
        self.selectors = selectors
        self.options = options
        self.kind = kind


class PriceSelector(SelectQuery, total=False):
    currency: Union[SelectQuery, str]
    amount: 'PriceSelector'
    format: Optional[str]


class StockStatusQuery(SelectQuery):
    in_stock: Union[str, list]
    out_of_stock: Union[str, list]
    buy_button: Optional[SelectQuery]


class StatusQuery(SelectQuery):
    enabled: Union[str, list]
    disabled: Union[str, list]


class JsSelector:
    js_data: dict
    final: bool = False
    transformers: dict[str, ITransformer]

    def __init__(self, js_input: Union[str, list[dict], None], final: bool = False, ld_json: bool = False,
                 transform: Optional[str] = None):
        self.final = final

        self.transformers = {
            "dummy": DummyTransformer(),
            "magento": MagentoTransformer()
        }

        if isinstance(js_input, str) and not final:
            if ld_json:
                # Make sure to remove any newlines and control characters as they may lead to malformed json
                # Removing newline, carriage return, tab, and other control characters
                input = re.sub(r'[\r\n\t]+', ' ', js_input)
                # Remove other control characters (ASCII 0-31 except space)
                input = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f]', '', input)
                # Parse LD+JSON - let it fail loudly if it can't be parsed after sanitization
                self.js_data = hjson.loads(input)
                if transform in self.transformers:
                    self.js_data = self.transformers[transform].transform(self.js_data)
            else:
                self.js_data = chompjs.parse_js_object(js_input)
                if transform in self.transformers:
                    self.js_data = self.transformers[transform].transform(self.js_data)
        else:
            self.js_data = js_input

    def select(self, selector: SelectQuery) -> SelectorList:
        if selector is None:
            return SelectorList([])
        if selector['type'] == '':
            return SelectorList([])
        if selector['type'] != 'js':
            raise ValueError('Not a JS selector')

        if self.final:
            return SelectorList([JsSelector(js_input=None, final=True, ld_json=False)])

        return SelectorList(self.js(selector['query']))

    def js(self, query: str) -> list['JsSelector']:
        # if we have empty data just return empty list
        if not self.js_data:
            return []
        merged = {}
        # Merge function fot all the keys into a single list
        mr = re.match(r'merge\((.*)\)', query)
        if mr:
            query = re.sub(r'merge\((.*)\)', '$.[*]', query)
            fields = jmespath.search(mr.group(1), self.js_data)
            # We merge by first keys only
            if fields:
                i = 0
                for obj in fields:
                    i += 1
                    # Check if fields[obj] is iterrable
                    if not isinstance(fields[obj], dict):
                        continue
                    for key in fields[obj]:
                        if key not in merged and i == 1:
                            merged[key] = {}
                        try:
                            merged[key][obj] = fields[obj][key]
                        except KeyError:
                            pass

        result = []
        selected_keys = []
        # We enable regex on keys as jsonpath_rw doesn't support it
        # Before parsing the query we neet to check for key regular expressions and process the JS data
        r = r'key_regex\((.*)\)'
        regex_matches = re.findall(r, query)
        if regex_matches:
            query = re.sub(r, '$.[*]', query)
            for match in regex_matches:
                mregex = re.compile(match)
                for key in self.js_data:
                    if re.match(mregex, key):
                        selected_keys.append(self.js_data[key])

        if merged:
            js_data = list(merged.values())
        elif selected_keys:
            js_data = selected_keys
        else:
            js_data = self.js_data

        for match in parse(query).find(js_data):
            if match.value is None:
                return []
            if isinstance(match.value, list):
                for item in match.value:
                    result.append(JsSelector(item))
            # Check if it's a scalar value and mark it as a final value in the next selector
            # In that way if we matched with a scalar we no longer query with selectors
            # We only return empty values for further queries
            # TODO Check dict as I moved it to the top match
            else:
                result.append(JsSelector(match.value, final=isinstance(match.value, (int, float, str, bool))))

        return result

    def get(self):
        return self.js_data


class Selector:
    selector: Union[ParselSelector, JsSelector, None]

    def __init__(self, text: str = None, selector: Union[ParselSelector, JsSelector, None] = None,
                 encoding: Optional[str] = None):
        if text is not None and selector is not None:
            raise RuntimeError(
                Exception('%s received both text and selector. This is not allowed' % self.__class__.__name__))
        if text is not None:
            # Optimize: only detect/fix encoding if needed
            if isinstance(text, str):
                # Fast path: encoding provided and text looks clean
                # Slow path: no encoding OR text shows mojibake patterns
                if should_detect_encoding(text, encoding):
                    # Do expensive HTML parsing to detect encoding
                    detected_encoding = detect_html_encoding(text)
                    # Fix encoding if mismatch detected
                    text = fix_html_encoding(text, detected_encoding=detected_encoding, transport_encoding=encoding)
                # else: trust the spider's encoding, skip detection
                self.selector = ParselSelector(text)
            else:
                # Backward compatibility for crawler call sites that pass Scrapy/Parsel selector-like
                # objects positionally, e.g. Selector(response).
                self.selector = text

        elif selector is not None:
            self.selector = selector
        else:
            raise RuntimeError(
                Exception('%s is missing text or selector.' % self.__class__.__name__))

    def select(self, selector: SelectQuery) -> SelectorList:
        if selector is None:
            return SelectorList([])

        try:
            if selector['type'] == '':
                return SelectorList([])
            if selector['type'] == 'css':
                return SelectorList(map(lambda s: Selector(selector=s), self.selector.css(selector['query'])))
            if selector['type'] == 'xpath':
                return SelectorList(map(lambda s: Selector(selector=s), self.selector.xpath(selector['query'])))
            if selector['type'] == 'js':
                if isinstance(self.selector, ParselSelector):
                    raise Exception("Js not supported for Parsel selectors")
        except KeyError:
            raise ValueError('Missing query parameter or type in selector')
        except ValueError as e:
            parsel_type = getattr(self.selector, 'type', 'unknown')
            body_preview = ''
            if isinstance(self.selector, ParselSelector):
                raw = self.selector.get()
                body_preview = (raw[:300] + '…') if raw and len(raw) > 300 else (raw or '')
            raise ValueError(
                f"Selector type mismatch: config requests type='{selector.get('type')}' "
                f"query='{selector.get('query')}', but the underlying ParselSelector "
                f"has type='{parsel_type}'. Body preview: {body_preview!r}"
            ) from e

    def get(self):
        return self.selector.get()

    def getall(self):
        return self.selector.getall()

    def xpath(self, query: str, namespaces: Any = None):
        if isinstance(self.selector, JsSelector):
            raise Exception("XPath not supported for JS selectors")
        return self.selector.xpath(query=query, namespaces=namespaces)

    def css(self, query: str):
        if isinstance(self.selector, JsSelector):
            raise Exception("XPath not supported for JS selectors")
        return self.selector.css(query=query)

    def js(self, query: str):
        if isinstance(self.selector, ParselSelector):
            raise Exception("Js not supported for Parsel selectors")

    def re(self, regex, replace_entities: bool = True):
        return self.selector.re(regex, replace_entities)

    def re_first(self, regex, default: Any = None, replace_entities: bool = True):
        return self.selector.re_first(regex, default, replace_entities)
