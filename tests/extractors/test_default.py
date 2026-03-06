import pytest
from pytest_mock import MockerFixture

from pricemind_extraction.extractors.default import DefaultExtractor, strip
from pricemind_extraction.selector import Selector
from tests.test_case import get_html


@pytest.fixture
def nolog_extractor(mocker: MockerFixture):
    logger = mocker.MagicMock()
    selector = Selector(get_html())
    return DefaultExtractor(selector, logger)


def test_extract_price_regex(nolog_extractor):
    price = nolog_extractor.extract_price({
        'type': 'css',
        'query': 'div.price s',
        'regex': '<s>(?:\\s+)?(\\d+)(?:\\s+)?<sup>(?:\\s+)?(\\d+)',
        'currency': 'BGN'
    })

    assert price.currency == 'BGN'
    assert price.amount_text == '10.99'


def test_extract_multiple_str(nolog_extractor):
    txt = nolog_extractor.extract_str({
        'type': 'css',
        'query': '#texts p::text',
    })

    assert len(txt) == 4
    assert txt[3] == 'FooBar text'


def test_extract_single_str(nolog_extractor):
    txt = nolog_extractor.extract_str({
        'type': 'css',
        'query': '#texts p.four-text::text',
    })

    assert txt == 'FooBar text'

    txt = nolog_extractor.extract_str({
        'type': 'css',
        'query': '#texts p.four-text::text',
    }, False)

    assert txt == 'FooBar text '

#
def test_extract_url(nolog_extractor):
    images = nolog_extractor.extract_url({
        'type': 'css',
        'query': '#images li img::attr(src)'
    }, 'http://via.placeholder.com/100x100')

    assert len(images) == 5

    assert images[0] == 'http://via.placeholder.com/100x100'
    assert images[1] == 'http://via.placeholder.com/200x200'

def test_extract_url_encoded(nolog_extractor):
    images = nolog_extractor.extract_url({
        'type': 'css',
        'query': '#images li img::attr(src)'
    }, 'http://via.placeholder.com/100x100')

    assert len(images) == 5

    assert images[3] == 'http://via.placeholder.com/%20400x400'

def test_extract_url_handles_encode_path_true(nolog_extractor):
    url = nolog_extractor.extract_url({
        'type': 'css',
        'query': '#images li img::attr(src)',
        'encode_path': True
    }, 'http://via.placeholder.com/100x100')

    assert url[0] == 'http://via.placeholder.com/100x100'
    assert url[3] == 'http://via.placeholder.com/%20400x400'
    # RFC_3986_PATH_SAFE keeps ':' unencoded, so path stays https:// not https%3A//
    assert url[4] == 'https://images.example.test/https://assets.example.test/media/catalog/product/frypan-24cm.tiff?timestamp=20240925095255&transform=v1/quality=70/resize=2000'


def test_extract_url_handles_encode_path_false(nolog_extractor):
    url = nolog_extractor.extract_url({
        'type': 'css',
        'query': '#images li img::attr(src)',
        'encode_path': False
    }, 'http://via.placeholder.com/100x100')

    assert url[0] == 'http://via.placeholder.com/100x100'
    assert url[3] == 'http://via.placeholder.com/ 400x400'
    assert url[4] == 'https://images.example.test/https://assets.example.test/media/catalog/product/frypan-24cm.tiff?timestamp=20240925095255&transform=v1/quality=70/resize=2000'


def test_strip():
    assert strip('test') == 'test'
    # assert strip('https://media.screwfix.com/is/image/ae235/?$p$&wid=281&hei=281&op_sharpen=1&layer=0&size=281,'
    #              '281&layer=1&size=281,281&src=ae235/1358J_P') == \
    #        'https://media.screwfix.com/is/image/ae235/?$p$&wid=281&hei=281&op_sharpen=1&layer=0&size=281,' \
    #        '281&layer=1&size=281,281&src=ae235/1358J_P '


def test_initial_status(nolog_extractor):
    query = {}
    result = nolog_extractor._extract_status_from_query(query, 'in_stock', 'out_of_stock', 2)
    assert result == 2, "Initial status should be 2"


def test_positive_string_condition(nolog_extractor):
    query = {'default': 'Available', 'in_stock': 'Available'}
    result = nolog_extractor._extract_status_from_query(query, 'in_stock', 'out_of_stock', 0)
    assert result == 1, "Status should be 1 for positive string condition"


def test_negative_string_condition(nolog_extractor):
    query = {'default': 'Unavailable', 'out_of_stock': 'Unavailable'}
    result = nolog_extractor._extract_status_from_query(query, 'in_stock', 'out_of_stock', 1)
    assert result == 0, "Status should be 0 for negative string condition"

# def test_negative_string_condition(nolog_extractor):
#     query = {'default': 'Unavailable', 'out_of_stock': 'Unavailable', 'in_stock': 'Available'}
#     result = nolog_extractor._extract_status_from_query(query, 'in_stock', 'out_of_stock', 1)
#     assert result == 0, "Status should be 0 for negative string condition"
def test_positive_bool_condition(nolog_extractor):
    query = {'default': 'True', 'in_stock': True}
    result = nolog_extractor._extract_status_from_query(query, 'in_stock', 'out_of_stock', 0)
    assert result == 1, "Status should be 1 for positive boolean condition"


def test_negative_bool_condition(nolog_extractor):
    query = {'default': 'False', 'out_of_stock': False}
    result = nolog_extractor._extract_status_from_query(query, 'in_stock', 'out_of_stock', 1)
    assert result == 0, "Status should be 0 for negative boolean condition"


def test_positive_int_condition(nolog_extractor):
    query = {'default': '1', 'in_stock': 1}
    result = nolog_extractor._extract_status_from_query(query, 'in_stock', 'out_of_stock', 0)
    assert result == 1, "Status should be 1 for positive integer condition"


def test_negative_int_condition(nolog_extractor):
    query = {'default': '0', 'out_of_stock': 0}
    result = nolog_extractor._extract_status_from_query(query, 'in_stock', 'out_of_stock', 1)
    assert result == 0, "Status should be 0 for negative integer condition"


def test_positive_float_condition(nolog_extractor):
    query = {'default': '1.0', 'in_stock': 1.0}
    result = nolog_extractor._extract_status_from_query(query, 'in_stock', 'out_of_stock', 0)
    assert result == 1, "Status should be 1 for positive float condition"


def test_negative_float_condition(nolog_extractor):
    query = {'default': '0.0', 'out_of_stock': 0.0}
    result = nolog_extractor._extract_status_from_query(query, 'in_stock', 'out_of_stock', 1)
    assert result == 0, "Status should be 0 for negative float condition"


class TestRegexFallbackBehavior:
    """
    Tests for multiple selector fallback behavior when regex doesn't match.
    
    This tests the scenario where we have multiple selectors with different regex patterns,
    and the extractor should fall through to the next selector when the regex doesn't match.
    
    Example use case: Extracting the first EAN barcode that doesn't start with '2' from a
    comma-separated list like "2612412015607,7612412156003,7612412424935"
    """

    @pytest.fixture
    def barcode_extractor_starts_with_2(self, mocker):
        """Extractor with barcode data where FIRST barcode starts with 2"""
        logger = mocker.MagicMock()
        html = '''
        <html><body>
        <table><tr><td data-th="Баркод">2612412015607,7612412156003,7612412424935</td></tr></table>
        </body></html>
        '''
        selector = Selector(text=html)
        return DefaultExtractor(selector, logger)

    @pytest.fixture
    def barcode_extractor_starts_with_7(self, mocker):
        """Extractor with barcode data where FIRST barcode starts with 7 (not 2)"""
        logger = mocker.MagicMock()
        html = '''
        <html><body>
        <table><tr><td data-th="Баркод">7612412015607,7612412156003,7612412424935</td></tr></table>
        </body></html>
        '''
        selector = Selector(text=html)
        return DefaultExtractor(selector, logger)

    @pytest.fixture
    def barcode_extractor_all_start_with_2(self, mocker):
        """Extractor with barcode data where ALL barcodes start with 2"""
        logger = mocker.MagicMock()
        html = '''
        <html><body>
        <table><tr><td data-th="Баркод">2612412015607,2612412156003,2612412424935</td></tr></table>
        </body></html>
        '''
        selector = Selector(text=html)
        return DefaultExtractor(selector, logger)

    @pytest.fixture
    def ean_config(self):
        """Config that tries to find first barcode not starting with 2"""
        return [
            {
                "type": "css",
                "query": "td[data-th=Баркод]::text",
                "regex": r"^\s*(?!2)(\d+)"
            },
            {
                "type": "css",
                "query": "td[data-th=Баркод]::text",
                "regex": r"^\s*\d+,\s*(?!2)(\d+)"
            },
            {
                "type": "css",
                "query": "td[data-th=Баркод]::text",
                "regex": r"^\s*\d+,\s*\d+,\s*(?!2)(\d+)"
            }
        ]

    def test_first_selector_matches_when_first_barcode_not_starting_with_2(
            self, barcode_extractor_starts_with_7, ean_config):
        """
        When first barcode doesn't start with 2, first selector should match.
        Input: 7612412015607,7612412156003,7612412424935
        Expected: 7612412015607 (first barcode)
        """
        result = barcode_extractor_starts_with_7.extract_str(ean_config)
        assert result == "7612412015607", \
            f"Expected first barcode '7612412015607', got '{result}'"

    def test_fallback_to_second_selector_when_first_barcode_starts_with_2(
            self, barcode_extractor_starts_with_2, ean_config):
        """
        When first barcode starts with 2, should fall through to second selector.
        Input: 2612412015607,7612412156003,7612412424935
        Expected: 7612412156003 (second barcode, first not starting with 2)
        """
        result = barcode_extractor_starts_with_2.extract_str(ean_config)
        assert result == "7612412156003", \
            f"Expected second barcode '7612412156003', got '{result}'"

    def test_fallback_to_third_selector_when_first_two_start_with_2(self, mocker, ean_config):
        """
        When first two barcodes start with 2, should fall through to third selector.
        Input: 2612412015607,2612412156003,7612412424935
        Expected: 7612412424935 (third barcode)
        """
        logger = mocker.MagicMock()
        html = '''
        <html><body>
        <table><tr><td data-th="Баркод">2612412015607,2612412156003,7612412424935</td></tr></table>
        </body></html>
        '''
        selector = Selector(text=html)
        extractor = DefaultExtractor(selector, logger)
        
        result = extractor.extract_str(ean_config)
        assert result == "7612412424935", \
            f"Expected third barcode '7612412424935', got '{result}'"

    def test_returns_none_when_all_barcodes_start_with_2(
            self, barcode_extractor_all_start_with_2, ean_config):
        """
        When all barcodes start with 2, no selector matches, should return None.
        Input: 2612412015607,2612412156003,2612412424935
        Expected: None (no barcode matches the criteria)
        """
        result = barcode_extractor_all_start_with_2.extract_str(ean_config)
        assert result is None, \
            f"Expected None when all barcodes start with 2, got '{result}'"

    def test_regex_no_match_returns_empty_list_which_is_falsy(self, mocker):
        """
        Verify that when regex doesn't match, _regex_extract returns empty list
        which evaluates as falsy, allowing fallthrough to next selector.
        """
        logger = mocker.MagicMock()
        html = '<html><body><span id="test">2612412015607</span></body></html>'
        selector = Selector(text=html)
        extractor = DefaultExtractor(selector, logger)
        
        query = {
            "type": "css",
            "query": "#test::text",
            "regex": r"^\s*(?!2)(\d+)"  # Won't match because starts with 2
        }
        
        # Test _regex_extract directly
        result = extractor._regex_extract(extractor.selector, query)
        assert result == [], f"Expected empty list, got {result}"
        assert not result, "Empty list should be falsy for fallthrough logic"

    def test_regex_match_returns_captured_group(self, mocker):
        """
        Verify that when regex matches, _regex_extract returns the captured group.
        """
        logger = mocker.MagicMock()
        html = '<html><body><span id="test">7612412015607</span></body></html>'
        selector = Selector(text=html)
        extractor = DefaultExtractor(selector, logger)
        
        query = {
            "type": "css",
            "query": "#test::text",
            "regex": r"^\s*(?!2)(\d+)"  # Will match because starts with 7
        }
        
        result = extractor._regex_extract(extractor.selector, query)
        assert result == ["7612412015607"], f"Expected ['7612412015607'], got {result}"

    def test_single_selector_with_non_matching_regex_returns_none(self, mocker):
        """
        Single selector with non-matching regex should return None from extract_str.
        """
        logger = mocker.MagicMock()
        html = '<html><body><span id="test">2612412015607</span></body></html>'
        selector = Selector(text=html)
        extractor = DefaultExtractor(selector, logger)
        
        config = {
            "type": "css",
            "query": "#test::text",
            "regex": r"^\s*(?!2)(\d+)"
        }
        
        result = extractor.extract_str(config)
        assert result is None, f"Expected None, got '{result}'"

    def test_multiple_text_nodes_with_regex(self, mocker):
        """
        Test behavior when CSS selector returns multiple separate text nodes.
        Each node is processed independently by the regex.
        """
        logger = mocker.MagicMock()
        html = '''
        <html><body>
        <div id="codes">
            <span>2612412015607</span>
            <span>7612412156003</span>
            <span>7612412424935</span>
        </div>
        </body></html>
        '''
        selector = Selector(text=html)
        extractor = DefaultExtractor(selector, logger)
        
        config = {
            "type": "css",
            "query": "#codes span::text",
            "regex": r"^\s*(?!2)(\d+)"
        }
        
        result = extractor.extract_str(config)
        # Should return all barcodes not starting with 2
        assert result == ["7612412156003", "7612412424935"], \
            f"Expected list of non-2-starting barcodes, got '{result}'"

    def test_barcode_with_leading_whitespace(self, mocker, ean_config):
        """
        Test that leading whitespace doesn't break the regex matching.
        """
        logger = mocker.MagicMock()
        html = '''
        <html><body>
        <table><tr><td data-th="Баркод">  2612412015607,7612412156003,7612412424935</td></tr></table>
        </body></html>
        '''
        selector = Selector(text=html)
        extractor = DefaultExtractor(selector, logger)
        
        result = extractor.extract_str(ean_config)
        assert result == "7612412156003", \
            f"Expected '7612412156003' even with leading whitespace, got '{result}'"

    def test_barcode_with_newlines_between(self, mocker):
        """
        Test handling of newline-separated barcodes.
        Note: The regex uses MULTILINE flag, so ^ matches at start of each line.
        """
        logger = mocker.MagicMock()
        html = '''
        <html><body>
        <table><tr><td data-th="Баркод">2612412015607
7612412156003
7612412424935</td></tr></table>
        </body></html>
        '''
        selector = Selector(text=html)
        extractor = DefaultExtractor(selector, logger)
        
        # With MULTILINE, ^ matches at the start of EACH line
        # So the first regex will match at the start of line 2 (7612412156003)
        config = {
            "type": "css",
            "query": "td[data-th=Баркод]::text",
            "regex": r"^\s*(?!2)(\d+)"
        }
        
        result = extractor.extract_str(config)
        # Due to MULTILINE flag, ^ can match at start of any line
        # So even with first line starting with 2, the regex finds 7612412156003 on line 2
        assert result == "7612412156003", \
            f"With MULTILINE flag, regex should match at start of second line, got '{result}'"

    def test_barcode_with_spaces_after_commas(self, mocker, ean_config):
        """
        Test handling of spaces after commas in the barcode list.
        """
        logger = mocker.MagicMock()
        html = '''
        <html><body>
        <table><tr><td data-th="Баркод">2612412015607, 7612412156003, 7612412424935</td></tr></table>
        </body></html>
        '''
        selector = Selector(text=html)
        extractor = DefaultExtractor(selector, logger)
        
        result = extractor.extract_str(ean_config)
        # The second regex has \s* after the comma which handles spaces
        assert result == "7612412156003", \
            f"Expected '7612412156003' with spaces after commas, got '{result}'"

    def test_exact_user_example_data(self, mocker, ean_config):
        """
        Test with the exact data from the user's example.
        """
        logger = mocker.MagicMock()
        html = '''
        <html><body>
        <table><tr><td data-th="Баркод">7612412015607,7612412156003,7612412424935</td></tr></table>
        </body></html>
        '''
        selector = Selector(text=html)
        extractor = DefaultExtractor(selector, logger)
        
        result = extractor.extract_str(ean_config)
        # Since none start with 2, the first regex should match the first barcode
        assert result == "7612412015607", \
            f"Expected first barcode '7612412015607', got '{result}'"
