import html
import re
import warnings
from urllib.parse import urljoin, quote, urlparse, urlunparse, unquote
from itertools import chain
from abc import ABC, abstractmethod
from typing import Callable, List, Union, Optional

# RFC 3986 path-safe characters that should not be percent-encoded
# unreserved = ALPHA / DIGIT / "-" / "." / "_" / "~"
# sub-delims = "!" / "$" / "&" / "'" / "(" / ")" / "*" / "+" / "," / ";" / "="
# pchar = unreserved / pct-encoded / sub-delims / ":" / "@"
# path = *( "/" / pchar )
RFC_3986_PATH_SAFE = "/:@!$&'()*+,;=-._~"

from parsel import SelectorList
from price_parser import Price, parse_price
from scutils.log_factory import LogObject
from slugify import slugify
from bs4 import BeautifulSoup

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


class IExtractor(ABC):
    selector: Selector

    @abstractmethod
    def select(self, query: Union[SelectQuery, None]) -> SelectorList[Union[Selector, JsSelector]]:
        pass

    @abstractmethod
    def get_selector(self, query: Union[SelectQuery, None]) -> Union[Selector, JsSelector]:
        pass

    @abstractmethod
    def extract_exists(self, paths: [SelectQuery, List[SelectQuery], SelectCollectionQuery]) -> bool:
        pass

    @abstractmethod
    def extract_str(self, paths: [SelectQuery, List[SelectQuery], SelectCollectionQuery, None],
                    should_strip: bool = True) -> Union[str, List[str], None]:
        pass

    @abstractmethod
    def extract_str_agg(self, paths: [SelectQuery, List[SelectQuery], SelectCollectionQuery, None],
                        should_strip: bool = True, separator: str = " ") -> Union[str, None]:
        pass

    @abstractmethod
    def extract_url(self, paths: [UrlQuery, List[UrlQuery], SelectCollectionQuery], base_url: str) -> Union[
        str, List[str], None]:
        pass

    @abstractmethod
    def extract_categories(self, path: [SelectQuery, List[SelectQuery], None, SelectCollectionQuery]) -> [List[str], None]:
        pass

    @abstractmethod
    def extract_price(self, paths: [PriceSelector, List[PriceSelector], None]) -> [Price, None]:
        pass

    @abstractmethod
    def extract_special_price(self, paths: [SelectQuery, List[SelectQuery]], original_price: Price) -> Price:
        pass

    @abstractmethod
    def extract_stock_status(self, stock_status_query: Optional[StockStatusQuery]) -> int:
        pass

    @abstractmethod
    def extract_status(self, stock_status_query: StatusQuery) -> int:
        pass

    @abstractmethod
    def clean(self):
        pass


class DefaultExtractor(IExtractor):
    selector: Selector
    listing_selector: Optional[Selector]
    local_selector: Optional[Selector]
    logger: LogObject
    _js_selectors: dict[str, JsSelector]

    def __init__(self, selector: Selector, logger, local_selector: Union[Selector, None] = None,
                 listing_selector: Union[Selector, None] = None):
        self.local_selector = local_selector
        self.listing_selector = listing_selector
        self.selector = selector
        self.logger = logger
        self._js_selectors = {}

    def select(self, query: Union[SelectQuery, None]) -> SelectorList[Union[Selector, JsSelector]]:
        return self.get_selector(query).select(query)

    def extract_exists(self, paths: [SelectQuery, List[SelectQuery], SelectCollectionQuery]) -> bool:
        """
        Pure selector-based existence check - determines if any selector finds actual content.
        
        This method is "pure" in that it only looks for real content via selectors:
        - Returns True only if a selector query finds actual data on the page
        - Returns False if selectors find None, empty strings, or no matches
        - Does NOT consider 'default' values when determining existence
        - Processes multiple selectors with OR logic (any selector finding content = True)
        
        Args:
            paths: Can be a single SelectQuery, list of SelectQuery, or SelectCollectionQuery
            
        Returns:
            bool: True if any selector finds actual content, False otherwise
            
        Examples:
            - Selector finds text "Available" -> True
            - Selector finds empty string "" -> False  
            - Selector finds None -> False
            - Selector with {'default': '1'} but no 'query' -> False
            - Multiple selectors where any one finds content -> True
        """
        # Normalize input: convert single selector or SelectCollectionQuery to list format
        if not isinstance(paths, list) and not isinstance(paths, SelectCollectionQuery):
            query = [paths]  # Single SelectQuery -> [SelectQuery]
        elif isinstance(paths, SelectCollectionQuery):
            query = paths.selectors  # Extract selectors from collection
        else:
            query = paths  # Already a list
            
        # Check each selector for actual content (OR logic: any selector with content = True)
        for q in query:
            try:
                selector = self.get_selector(q)
                result = selector.select(q).get()  # Execute the selector query
            except ValueError as e:
                raise ValueError(
                    f"extract_exists failed for selector config {q!r}: {e}"
                ) from e
            
            # Float values are always considered as existing content
            if isinstance(result, float):
                return True
                
            # Check if we have actual content (not None and not empty)
            if result is not None and len(str(result)) > 0:
                return True
                
        # No selector found any content
        return False

    def extract_str(
            self,
            paths: [SelectQuery, List[SelectQuery], SelectCollectionQuery, None],
            should_strip: bool = True
    ) -> Union[str, List[str], None]:
        """
        :param should_strip:
        :param paths:
        :return:
        """
        if paths is None:
            return None

        result = self._extract(paths, self._regex_extract, should_strip)

        if isinstance(result, bool):
            result = str(result).lower()
        elif not isinstance(result, list):
            result = str(result)

        res_len = len(result)
        if res_len == 0:
            return None

        if isinstance(result, list) and res_len == 1:
            return result[0]

        return result

    def extract_str_agg(self,
                        paths: [SelectQuery, List[SelectQuery], SelectCollectionQuery, None],
                        should_strip: bool = True,
                        separator: str = " ") -> Union[str, None]:
        s = self.extract_str(paths, should_strip)
        if isinstance(s, list):
            return separator.join(s)
        return s

    def extract_url(self, paths: Union[UrlQuery, List[UrlQuery], SelectCollectionQuery], base_url: str) -> Union[
        str, List[str], None]:
        """
        Extracts and processes URLs from the given paths.

        :param paths: The URL paths to process. Can be a single path, a list of paths, or a collection query.
                      Each path can be a string or a dictionary containing an 'encode_path' key.
        :param base_url: The base URL to use for relative URLs.
        :return: A processed URL or a list of processed URLs.
        """

        def process_url(url: str, encode_path: bool) -> str:
            """
            Processes a single URL, handling path encoding and absolute/relative URLs.

            :param url: The URL to process.
            :param encode_path: If True, URL-encode the path of the URL.
            :return: The processed URL as a string.
            """
            # Parse the input URL
            parsed = urlparse(url)

            # Decode the path to handle spaces and special characters
            decoded_path = unquote(parsed.path.strip())

            # Conditionally encode the path
            if encode_path:
                encoded_path = quote(decoded_path, safe=RFC_3986_PATH_SAFE)
            else:
                encoded_path = decoded_path

            # Reconstruct the URL with the (possibly encoded) path
            reconstructed_url = urlunparse(parsed._replace(path=encoded_path))

            # Check if the URL is absolute
            if parsed.scheme and parsed.netloc:
                return str(reconstructed_url)
            else:
                # Join the base URL with the reconstructed URL if it's a relative URL
                return urljoin(base_url, str(reconstructed_url))

        # Extract URLs from the paths without stripping them
        urls = self.extract_str(paths)

        encode_path = True

        if isinstance(paths, list):
            # Make encode path false if it is false in any of the paths
            # TODO: To fix this make the _extract method return the index of the user selector so that we
            for path in paths:
                if isinstance(path, dict):
                    encode_path = path.get('encode_path', True)
                else:
                    encode_path = True
                if not encode_path:
                    break
        elif isinstance(paths, dict):
            encode_path = paths.get('encode_path', True)

        # Handle cases where URLs are None or empty
        if urls is None:
            return ""
        if len(urls) == 0:
            return None

        # Process a list of URLs
        if isinstance(urls, list):
            processed_urls = []
            for url in urls:
                # Process the URL with the specified encode_path setting
                processed_urls.append(process_url(url, encode_path))
            return processed_urls

        # Process a single URL
        else:
            # Process the URL with the specified encode_path setting
            return process_url(urls, encode_path)

    def extract_categories(
            self,
            path: [SelectQuery, List[SelectQuery], None, SelectCollectionQuery]
    ) -> [List[str], None]:
        """
        Extracts categories
        :param path:
        :return:
        """
        if path:
            if isinstance(path, SelectCollectionQuery):
                strategy = path.strategy or 'first'
                results = []
                for p in path.selectors:
                    res = self.extract_categories(p)
                    if strategy == 'first' and res:
                        return res
                    if res:
                        results.append(res)
                if strategy == 'all':
                    return list(chain.from_iterable(results)) if results else None
                return None

            if isinstance(path, list):
                for p in path:
                    res = self.extract_categories(p)
                    if res:
                        return res
                return None

            result = list(map(strip, self.get_selector(path).select(path).getall()))
            return result if result else None

        return None

    def extract_price(self, paths: [PriceSelector, List[PriceSelector], None]) -> Optional[Price]:
        """
        Extracts price from passed selectors
        :param paths:
        :return:
        """
        if paths is None:
            return None
        price_str = self._extract(paths, self._regex_price_extract, False)

        return parse_price(str(price_str))

    def extract_special_price(self, paths: [SelectQuery, List[SelectQuery]], original_price: Price) -> Price:
        """
        Extracts special price and validates original
        deprecated
        :param paths:
        :param original_price:
        :return:
        :deprecated:
        """
        warnings.warn('This function is deprecated', DeprecationWarning)
        sp = self.extract_price(paths)
        # Special price is greater or equal which is incorrect
        if isinstance(sp.amount_float, (int, float)) and sp.amount_float >= original_price.amount_float:
            return Price.fromstring("")
        return sp

    def extract_stock_status(self, stock_status_query: Optional[StockStatusQuery]) -> int:
        if not stock_status_query:
            return 2

        try:
            buy_button = self.extract_str(stock_status_query['buy_button'])
        except KeyError:
            buy_button = None

        if buy_button:
            initial_status = 1
        elif 'buy_button' in stock_status_query:
            initial_status = 0
        else:
            initial_status = 2

        if 'default' in stock_status_query:
            if isinstance(stock_status_query['default'], str) and stock_status_query['default'].isnumeric():
                initial_status = int(stock_status_query['default'])
            elif isinstance(stock_status_query['default'], int):
                initial_status = stock_status_query['default']

        if 'query' not in stock_status_query:
            stock_status_query = None
        try:
            return self._extract_status_from_query(stock_status_query, 'in_stock', 'out_of_stock', initial_status)
        except Exception:
            self.logger.error('Failed to extract stock status as of exception', exc_info=True)
            return initial_status

    def extract_status(self, stock_status_query: StatusQuery) -> int:
        return self._extract_status_from_query(stock_status_query, 'enabled', 'disabled', 1)

    from typing import Optional, Union, List

    def _extract_status_from_query(self, query: Optional[dict], positive_key: str, negative_key: str,
                                   initial_status: int) -> int:
        # Initialize the status with the given initial status
        status = initial_status

        # Proceed only if the query is not None
        if query:
            # Initialize a flag for missing stock status element
            missing_stock_status_element = False

            # Extract only the selector part from the query for extraction
            # The query contains both the selector keys and status configuration keys
            selector_keys = {'query', 'type', 'js', 'scope', 'regex', 'regex_replace', 'default', 'encode_path'}
            selector_query = {k: v for k, v in query.items() if k in selector_keys}
            
            # Extract stock status as a string using only the selector part
            stock_status_str = self.extract_str(selector_query)

            if isinstance(stock_status_str, list):
                if len(stock_status_str) == 1:
                    stock_status_str = stock_status_str[0]
                elif len(stock_status_str) == 0:
                    stock_status_str = None
                else:
                    raise ValueError('Bad stock status string selector %s' % query)

                    # Set the missing flag if no stock status string is found
            if not stock_status_str:
                missing_stock_status_element = True

            # If stock status string is missing but default is provided, use the default
            if missing_stock_status_element and 'default' in query:
                stock_status_str = str(query['default'])

            # Function to check if the current status matches any status in the list or single status
            def check_status(status_list_or_value):
                # Convert single scalar value to list for uniform handling
                if not isinstance(status_list_or_value, list):
                    status_list_or_value = [status_list_or_value]

                # Iterate through the list and check if any value matches the current stock status
                for one_status in status_list_or_value:
                    if isinstance(one_status, str):
                        # Case for string comparison (ignoring case)
                        if one_status.lower() in stock_status_str.lower():
                            return True
                    elif isinstance(one_status, bool):
                        # Case for boolean comparison
                        if str(one_status).lower() == stock_status_str.lower():
                            return True
                    elif isinstance(one_status, (int, float)):
                        # Case for numeric comparison
                        try:
                            if float(one_status) == float(stock_status_str):
                                return True
                        except ValueError:
                            pass  # Ignore conversion error, proceed with next

                # No match found, return False
                return False

            # Check for positive conditions
            if positive_key in query and check_status(query[positive_key]):
                return 1

            # Check for negative conditions
            if negative_key in query and check_status(query[negative_key]):
                return 0

        return status

    def _extract(self,
                 selectors: Union[
                     SelectQuery, PriceSelector, List[Union[SelectQuery, PriceSelector]], SelectCollectionQuery
                 ],
                 callback: Callable[[Selector, Union[SelectQuery, PriceSelector]], any],
                 should_strip: bool = True) -> Union[str, float, int, List[Union[str, float, int]]]:
        """

        :param selectors:
        :param callback:
        :return:
        """
        strategy = 'first'
        selector_options = None
        if isinstance(selectors, SelectCollectionQuery):
            strategy = selectors.strategy
            try:
                selector_options = selectors.options
            except AttributeError:
                selector_options = None
            selectors = selectors.selectors

        if not isinstance(selectors, list):
            selectors = [selectors]

        results = [None] * len(selectors)
        i = 0
        for selector in selectors:
            default = selector.get('default', None)
            if default is not None and 'query' not in selector:
                return default
            try:
                result = callback(self.get_selector(selector), selector)
            except (ValueError, TypeError) as e:
                raise ValueError(
                    f"Extraction failed for selector [{i}/{len(selectors)}] "
                    f"type='{selector.get('type')}' query='{selector.get('query', '')}' "
                    f"scope='{selector.get('scope', '')}' "
                    f"js={'yes' if 'js' in selector else 'no'}: {e}"
                ) from e
            if isinstance(result, bool):
                result = str(result).lower()
            if isinstance(result, list):
                if should_strip:
                    result = list(map(lambda s: str(s).lower() if (isinstance(s, bool)) else strip(str(s)), result))
                results[i] = result
            elif isinstance(result, (str, float, int)):
                if should_strip and isinstance(result, str):
                    result = strip(result)
                results[i] = result
            if strategy == 'first' and result:
                break
            i += 1

        if strategy == 'all':
            # If the result is a list we need to flatten it to one level and make it unique
            if isinstance(results, list):
                return list(set(list(chain.from_iterable(results))))
            return results
        elif strategy == 'concat':
            separator = selector_options['separator'] if (selector_options and 'separator' in selector_options) else '-'

            if isinstance(results, list):
                # Flatten the list, remove duplicates, and filter out None and empty strings
                flattened_results = chain.from_iterable(results)
                unique_results = dict.fromkeys(flattened_results)
                filtered_results = [item for item in unique_results if item not in (None, '')]
                return separator.join(filtered_results)
            else:
                # Filter out None and empty strings from results
                filtered_results = [item for item in results if item not in (None, '')]
                return separator.join(filtered_results)

            #     return separator.join(set(list(chain.from_iterable(results))))
            # return separator.join(results)

        else:
            try:
                return results[i] if results[i] else ""
            except IndexError:
                return ""

    @staticmethod
    def _regex_extract(selector: Selector, query: SelectQuery) -> Union[str, List[str]]:
        result = selector.select(query).getall()
        if len(result) == 0:
            return query.get('default', [])
        if 'regex' in query and len(query['regex']) > 0:
            if isinstance(result, list):
                result = list(filter(
                    lambda r: r is not None,
                    map(lambda r: r.group(1) if (r is not None) else None,
                        map(lambda r: re.search(query['regex'], r, re.MULTILINE), result))
                ))
            else:
                match = re.search(query['regex'], result)
                if match is not None:
                    result = match.group(1)
        if 'regex_replace' in query and len(query['regex_replace']) > 0:
            pattern = re.compile(query['regex_replace']['pattern'])
            replacement = query['regex_replace']['replacement']
            if isinstance(result, list):
                result = list(map(lambda r: re.sub(pattern, replacement, r), result))
            else:
                result = re.sub(pattern, replacement, result)

        return result

    def _regex_price_extract(self, selector: Selector, query: Union[PriceSelector, None]) -> str:
        if query is None:
            return ''

        # Check if the query is a ::text (css)
        if 'query' in query and '::text' in query['query']:
            price_str = selector.select(query).getall()
            price_str = ' '.join(price_str)
        else:
            price_str = selector.select(query).get()

        if 'amount' in query and price_str:
            sub_extractor = DefaultExtractor(selector=Selector(text=price_str),
                                             logger=self.logger)
            price = sub_extractor.extract_str(query['amount'])

            if 'currency' in query:
                currency = sub_extractor.extract_str(query['currency'])
                return '{} {}'.format(price, currency).strip()

            if 'format' in query:
                if query['format'] == 'int' and price is not None:
                    price = str(int(price) / 100)

            return price
        elif 'regex' in query and len(query['regex']) > 0 and price_str:
            price_str = re.sub('[\n\r\t]+', '', html.unescape(price_str))
            price_str = re.sub(r'\s+', ' ', price_str)
            p = re.compile(query['regex'], re.MULTILINE)
            m = p.search(price_str)
            if m is None:
                self.logger.warning(
                    'Cannot extract price. Price string is {}. Applied regex is {}'.format(price_str,
                                                                                           query['regex']))
                return ''
            g = m.groups()
            group_len = len(g)
            currency = ''
            if group_len in [2, 3]:
                if 'currency' in query:
                    currency = query['currency']
                    if group_len == 3 and currency != '':
                        m1 = re.sub(r'[\.,]', '', m[1])
                        m2 = re.sub(r'[\.,]', '', m[2])
                        m3 = re.sub(r'[\.,]', '', m[3])
                        return '{}{}.{} {}'.format(m1, m2, m3, currency).strip()
                elif group_len == 3:
                    currency = m[3]
                # remove dots and commas from the first part for the number
                m1 = re.sub(r'[\.,]', '', m[1])
                return '{}.{} {}'.format(m1, m[2], currency).strip()
            elif group_len == 1:
                if m[1] is None:
                    self.logger.warning(
                        'Cannot extract price due to missing value in first capturing group. Price string is {}. Applied regex is {}'.format(
                            price_str,
                            query['regex']))
                    return ''
                return re.sub(r'[\.,]', '', m[1])
            else:
                self.logger.warning(
                    'Cannot extract price expecting two or more groups. Price string is {}. Applied regex is {}'.format(
                        price_str,
                        query['regex']))
                return ''

        if 'format' in query:
            if query['format'] == 'int' and price_str is not None:
                price_str = str(int(price_str) / 100)

        return price_str

    def get_selector(self, query: Union[SelectQuery, None]) -> Union[Selector, JsSelector]:
        if query is None:
            return self.selector

        if 'js' in query:
            k = slugify(query['js']['query'])
            if k in self._js_selectors:
                return self._js_selectors[k]
            js_data = self.select(query['js']).get()

            ld_json = query['js'].get('ldjson', False)
            transform = query['js'].get('transform', None)

            self._js_selectors[k] = JsSelector(js_input=js_data, ld_json=ld_json, transform=transform)
            return self._js_selectors[k]
        scope = query.get('scope', 'local')
        if scope == 'local' and self.local_selector:
            return self.local_selector
        if scope == 'listing' and self.listing_selector:
            return self.listing_selector

        return self.selector

    def clean(self):
        self._js_selectors = {}


def strip(s: str) -> str:
    stripped_str = strip_tags(s)
    # normalise new lines
    stripped_str = re.sub('[\n\r\t]+', '\n', stripped_str)
    return stripped_str


def strip_newline(s: str) -> str:
    return re.sub(r'[\n]+', '', s).strip()


def strip_tags(html: str) -> str:
    soup = BeautifulSoup(html, 'html.parser')
    text_elements = soup.find_all(text=True)
    extracted_text = '\n'.join(element.strip() for element in text_elements if element.strip())
    return extracted_text
