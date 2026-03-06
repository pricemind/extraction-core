"""
HTML encoding detection and fixing utilities.

Separated into its own module to avoid circular imports.
"""
import re
from typing import Optional

from bs4 import BeautifulSoup


def _has_mojibake_patterns(text: str) -> bool:
    """
    Quick heuristic check for mojibake (garbled text from incorrect encoding).
    Does NOT parse HTML - just checks for common patterns.
    
    Common mojibake patterns:
    - Windows-1251 Cyrillic decoded as UTF-8: Ð, Ñ, Ò, Ó, Ô, Õ, Ö
    - UTF-8 double-encoded: Ã, â, Â, Ã‚, Ã¢
    - ISO-8859-1 issues: Ã©, Ã¨, Ã 
    
    Args:
        text: Sample text to check (usually first 16KB to handle large head sections)
        
    Returns:
        True if text shows signs of encoding corruption
    """
    if not text or len(text) < 10:
        return False
    
    # Check first 16KB for performance
    # Some sites (e.g. pazaruvaj.com) have 200KB+ head sections with title at the end
    # 16KB is a reasonable balance between catching edge cases and performance
    sample = text[:16384]
    
    # Common mojibake character sequences
    # These appear when Cyrillic/special chars are decoded with wrong encoding
    mojibake_indicators = [
        'Ð', 'Ñ', 'Ò', 'Ó', 'Ô', 'Õ', 'Ö', '×', 'Ø',  # Cyrillic → UTF-8 wrong decode (uppercase)
        'ð', 'ñ', 'ò', 'ó', 'ô', 'õ', 'ö', '÷', 'ø',  # Cyrillic → UTF-8 wrong decode (lowercase)
        'Ã‚', 'Ã', 'â€', 'Â',  # Double encoding
        'Ã©', 'Ã¨', 'Ã§',  # Latin extended wrong decode
        'Ã¼', 'Ã¶', 'Ã¤',  # German umlauts wrong decode
        'å', 'í', 'à', 'ï',  # More windows-1251 mojibake patterns
    ]
    
    # Count how many mojibake patterns we see
    matches = sum(1 for pattern in mojibake_indicators if pattern in sample)
    
    # If we see 2+ different mojibake patterns, likely corrupted
    # (1 pattern could be legitimate text)
    return matches >= 2


def should_detect_encoding(text: str, transport_encoding: Optional[str]) -> bool:
    """
    Determine if we need to do full HTML parsing for encoding detection.
    Uses lightweight checks first to avoid unnecessary parsing.
    
    Fast path (skip detection):
    - Encoding provided + text looks clean
    
    Slow path (do detection):
    - No encoding provided
    - Text shows mojibake patterns
    
    Args:
        text: HTML content
        transport_encoding: Encoding from spider/transport
        
    Returns:
        True if we should parse HTML to detect encoding
    """
    if not text:
        return False
    
    # If no encoding info from spider, we must detect
    if not transport_encoding:
        return True
    
    # If encoding provided, check if text looks corrupted
    # Only do expensive HTML parsing if we see mojibake
    return _has_mojibake_patterns(text)


def detect_html_encoding(html: str) -> Optional[str]:
    """
    Detect HTML encoding from meta tags using proper HTML parsing.
    Looks for charset in meta http-equiv or meta charset attributes.
    
    Args:
        html: HTML content as string
        
    Returns:
        Detected encoding name (e.g., 'windows-1251', 'utf-8') or None if not found
    """
    if not html or not isinstance(html, str):
        return None
    
    try:
        # Parse only the head section for performance (encoding is always in head)
        # Use html.parser which is built-in and doesn't require lxml
        # Extract first 16KB to handle sites with large head sections (scripts, styles, etc.)
        # Some sites (e.g. pazaruvaj.com) have 200KB+ heads with title near the end
        head_content = html[:16384]
        soup = BeautifulSoup(head_content, 'html.parser')
        
        # Method 1: Look for <meta charset="...">
        meta_charset = soup.find('meta', charset=True)
        if meta_charset and meta_charset.get('charset'):
            encoding = meta_charset['charset'].strip()
            if encoding:
                return encoding.lower()
        
        # Method 2: Look for <meta http-equiv="Content-Type" content="text/html; charset=...">
        meta_http_equiv = soup.find('meta', attrs={'http-equiv': re.compile(r'^content-type$', re.IGNORECASE)})
        if meta_http_equiv and meta_http_equiv.get('content'):
            content = meta_http_equiv['content']
            # Parse charset from content attribute: "text/html; charset=windows-1251"
            if 'charset=' in content.lower():
                parts = content.lower().split('charset=')
                if len(parts) > 1:
                    # Extract charset value (might have quotes, semicolons, etc.)
                    charset = parts[1].split(';')[0].split()[0].strip('\'" \t\r\n')
                    if charset:
                        return charset.lower()
        
        return None
        
    except Exception:
        # If parsing fails, return None (don't break the entire process)
        # This is a best-effort detection
        return None


def fix_html_encoding(html: str, detected_encoding: Optional[str] = None, 
                      transport_encoding: Optional[str] = None) -> str:
    """
    Fix HTML encoding by re-encoding and decoding with the correct charset.
    
    SAFETY: Only applies the fix when there's evidence of encoding mismatch.
    If transport_encoding matches detected_encoding, assumes text is already correct.
    
    If the HTML was incorrectly decoded (e.g., as UTF-8 when it should be Windows-1251),
    we can recover it by re-encoding the string to bytes using 'latin1' (which can represent
    any byte value) and then decoding with the correct encoding.
    
    This works because when a string is incorrectly decoded, the Unicode code points
    correspond to the original byte values. Re-encoding with latin1 recovers those bytes.
    
    Args:
        html: HTML content as string (potentially incorrectly decoded)
        detected_encoding: Encoding detected from HTML meta tags
        transport_encoding: Encoding from transport/response metadata (what Scrapy used)
        
    Returns:
        Correctly decoded HTML string
    """
    # If no detected encoding, nothing to fix
    if not detected_encoding:
        return html
    
    # Normalize encoding names for comparison
    def normalize_encoding(enc):
        if not enc:
            return None
        enc = enc.lower().replace('-', '').replace('_', '').replace(' ', '')
        # Normalize common aliases
        aliases = {
            'windows1251': 'cp1251',
            'iso88591': 'latin1',
            'utf8': 'utf8',
        }
        return aliases.get(enc, enc)
    
    detected_norm = normalize_encoding(detected_encoding)
    transport_norm = normalize_encoding(transport_encoding) if transport_encoding else None
    
    # If transport encoding matches detected encoding, text is likely already correct
    # Don't apply fix to avoid double-decoding corruption!
    if transport_norm and transport_norm == detected_norm:
        return html
    
    # If detected encoding is UTF-8 and we have no transport encoding info, assume it's correct
    if detected_norm in ('utf8', 'utf-8') and not transport_encoding:
        return html
    
    # At this point, we have a mismatch:
    # - Transport says one encoding (or UTF-8 by default)
    # - HTML meta tag says different encoding
    # This suggests Scrapy might have mis-detected. Try to fix.
    
    # Map to proper encoding name
    encoding_map = {
        'windows_1251': 'windows-1251',
        'cp1251': 'windows-1251',
        'iso_8859_1': 'iso-8859-1',
        'latin1': 'iso-8859-1',
        'latin_1': 'iso-8859-1',
    }
    
    # Get proper encoding name
    detected_lower = detected_encoding.lower().replace('-', '_').replace(' ', '')
    proper_encoding = encoding_map.get(detected_lower, detected_encoding)
    
    try:
        # Try to fix: re-encode with latin1 (preserves bytes 0-255), then decode with correct encoding
        # This only works if the text was incorrectly decoded as latin1/UTF-8
        html_bytes = html.encode('latin1')
        return html_bytes.decode(proper_encoding)
    except (UnicodeEncodeError, UnicodeDecodeError, LookupError):
        # If encoding fails, return original HTML
        # The text might already be correctly decoded, or contains non-latin1 characters
        return html

