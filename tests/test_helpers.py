import unittest
from pricemind_extraction.encoding import (
    _has_mojibake_patterns,
    detect_html_encoding,
    fix_html_encoding,
    should_detect_encoding,
)


class TestDetectHtmlEncoding(unittest.TestCase):
    """Test cases for detect_html_encoding function"""

    def test_meta_charset_simple(self):
        """Test simple <meta charset="..."> detection"""
        html = '<html><head><meta charset="windows-1251"></head><body>Test</body></html>'
        result = detect_html_encoding(html)
        self.assertEqual(result, 'windows-1251')

    def test_meta_charset_uppercase(self):
        """Test uppercase charset name"""
        html = '<html><head><meta charset="UTF-8"></head><body>Test</body></html>'
        result = detect_html_encoding(html)
        self.assertEqual(result, 'utf-8')

    def test_meta_charset_single_quotes(self):
        """Test single quotes in charset attribute"""
        html = "<html><head><meta charset='windows-1251'></head><body>Test</body></html>"
        result = detect_html_encoding(html)
        self.assertEqual(result, 'windows-1251')

    def test_meta_charset_no_quotes(self):
        """Test charset without quotes"""
        html = '<html><head><meta charset=windows-1251></head><body>Test</body></html>'
        result = detect_html_encoding(html)
        self.assertEqual(result, 'windows-1251')

    def test_meta_http_equiv_standard(self):
        """Test standard <meta http-equiv="Content-Type" content="..."> format"""
        html = '<html><head><meta http-equiv="Content-Type" content="text/html; charset=windows-1251"></head></html>'
        result = detect_html_encoding(html)
        self.assertEqual(result, 'windows-1251')

    def test_meta_http_equiv_case_insensitive(self):
        """Test case-insensitive http-equiv attribute"""
        html = '<html><head><meta HTTP-EQUIV="content-type" CONTENT="text/html; charset=Windows-1251"></head></html>'
        result = detect_html_encoding(html)
        self.assertEqual(result, 'windows-1251')

    def test_meta_http_equiv_reversed_attributes(self):
        """Test reversed attribute order (content before http-equiv)"""
        html = '<html><head><meta content="text/html; charset=iso-8859-1" http-equiv="Content-Type"></head></html>'
        result = detect_html_encoding(html)
        self.assertEqual(result, 'iso-8859-1')

    def test_meta_http_equiv_with_spaces(self):
        """Test charset with extra spaces"""
        html = '<html><head><meta http-equiv="Content-Type" content="text/html;  charset=windows-1251  "></head></html>'
        result = detect_html_encoding(html)
        self.assertEqual(result, 'windows-1251')

    def test_meta_http_equiv_multiline(self):
        """Test multiline meta tag"""
        html = '''<html><head>
        <meta 
            http-equiv="Content-Type" 
            content="text/html; charset=windows-1251"
        >
        </head></html>'''
        result = detect_html_encoding(html)
        self.assertEqual(result, 'windows-1251')

    def test_multiple_meta_tags_first_wins(self):
        """Test that first valid meta tag is used"""
        html = '''<html><head>
        <meta charset="windows-1251">
        <meta charset="utf-8">
        </head></html>'''
        result = detect_html_encoding(html)
        self.assertEqual(result, 'windows-1251')

    def test_no_encoding_meta_tag(self):
        """Test HTML without encoding meta tag"""
        html = '<html><head><title>Test</title></head><body>Test</body></html>'
        result = detect_html_encoding(html)
        self.assertIsNone(result)

    def test_empty_html(self):
        """Test empty HTML string"""
        result = detect_html_encoding('')
        self.assertIsNone(result)

    def test_none_html(self):
        """Test None input"""
        result = detect_html_encoding(None)
        self.assertIsNone(result)

    def test_malformed_html(self):
        """Test malformed HTML"""
        html = '<html><head><meta charset="windows-1251"</head><body>Test'
        result = detect_html_encoding(html)
        # Should still work because BeautifulSoup handles malformed HTML
        self.assertEqual(result, 'windows-1251')

    def test_meta_tag_in_body(self):
        """Test that meta tag in body IS detected (BeautifulSoup finds it in first 4KB)"""
        html = '<html><head><title>Test</title></head><body><meta charset="windows-1251">Test</body></html>'
        result = detect_html_encoding(html)
        # BeautifulSoup will find it even if it's in body (within first 4KB)
        # This is actually fine - meta tags should be in head anyway
        self.assertEqual(result, 'windows-1251')

    def test_encoding_in_fragment(self):
        """Test HTML fragment without html/head tags"""
        html = '<meta charset="windows-1251"><title>Test</title>'
        result = detect_html_encoding(html)
        self.assertEqual(result, 'windows-1251')

    def test_common_encodings(self):
        """Test detection of common encodings"""
        test_cases = [
            ('utf-8', 'utf-8'),
            ('iso-8859-1', 'iso-8859-1'),
            ('windows-1252', 'windows-1252'),
            ('cp1251', 'cp1251'),
            ('shift_jis', 'shift_jis'),
            ('euc-jp', 'euc-jp'),
        ]
        for encoding, expected in test_cases:
            html = f'<html><head><meta charset="{encoding}"></head></html>'
            result = detect_html_encoding(html)
            self.assertEqual(result, expected.lower(), f"Failed for encoding {encoding}")

    def test_charset_with_semicolon(self):
        """Test charset followed by semicolon in content"""
        html = '<html><head><meta http-equiv="Content-Type" content="text/html; charset=windows-1251; boundary=xyz"></head></html>'
        result = detect_html_encoding(html)
        self.assertEqual(result, 'windows-1251')

    def test_large_html_document(self):
        """Test that only first 4KB is parsed for performance"""
        # Create a large HTML with meta tag in head
        html = '<html><head><meta charset="windows-1251"></head><body>' + 'x' * 10000 + '</body></html>'
        result = detect_html_encoding(html)
        self.assertEqual(result, 'windows-1251')

    def test_meta_tag_between_4kb_and_16kb(self):
        """Test that meta tag between 4KB-16KB IS detected (since we now check 16KB)"""
        # Create HTML with meta tag at ~10KB
        html = '<html><head>' + ' ' * 10000 + '<meta charset="windows-1251"></head></html>'
        result = detect_html_encoding(html)
        # Should be detected because it's within 16KB
        self.assertEqual(result, 'windows-1251')
    
    def test_meta_tag_after_16kb(self):
        """Test that meta tag after 16KB is NOT detected"""
        # Create HTML with meta tag after 16KB
        html = '<html><head>' + ' ' * 17000 + '<meta charset="windows-1251"></head></html>'
        result = detect_html_encoding(html)
        # Should be None because meta tag is after 16KB
        self.assertIsNone(result)

    def test_special_characters_in_html(self):
        """Test HTML with special characters before meta tag"""
        html = '<!-- Comment with юникод --><html><head><meta charset="windows-1251"></head></html>'
        result = detect_html_encoding(html)
        self.assertEqual(result, 'windows-1251')

    def test_meta_tag_with_extra_attributes(self):
        """Test meta tag with additional attributes"""
        html = '<html><head><meta name="viewport" charset="windows-1251" content="width=device-width"></head></html>'
        result = detect_html_encoding(html)
        self.assertEqual(result, 'windows-1251')

    def test_invalid_encoding_name(self):
        """Test that function returns the encoding even if it's invalid"""
        html = '<html><head><meta charset="invalid-encoding-xyz"></head></html>'
        result = detect_html_encoding(html)
        # Should return the value as-is (validation happens elsewhere)
        self.assertEqual(result, 'invalid-encoding-xyz')


class TestFixHtmlEncoding(unittest.TestCase):
    """Test cases for fix_html_encoding function"""

    def test_no_detected_encoding(self):
        """Test with no detected encoding"""
        html = "Test content Цена"
        result = fix_html_encoding(html, detected_encoding=None)
        self.assertEqual(result, html)

    def test_matching_encodings(self):
        """Test when transport and detected encodings match"""
        html = "Test content Цена"
        result = fix_html_encoding(html, detected_encoding='windows-1251', transport_encoding='windows-1251')
        self.assertEqual(result, html)

    def test_utf8_detected_no_transport(self):
        """Test UTF-8 detected with no transport encoding"""
        html = "Test content"
        result = fix_html_encoding(html, detected_encoding='utf-8')
        self.assertEqual(result, html)

    def test_encoding_mismatch_fix(self):
        """Test fixing windows-1251 incorrectly decoded as UTF-8"""
        # Simulate windows-1251 text incorrectly decoded as UTF-8/latin1
        # The Cyrillic word "Цена" in windows-1251 bytes: [0xD6, 0xE5, 0xED, 0xE0]
        # When incorrectly decoded as latin1, becomes: "Öåíà"
        incorrectly_decoded = "Öåíà"
        
        result = fix_html_encoding(
            incorrectly_decoded,
            detected_encoding='windows-1251',
            transport_encoding='utf-8'  # Mismatch triggers fix
        )
        
        # Should be fixed to proper Cyrillic
        self.assertEqual(result, "Цена")

    def test_encoding_aliases_normalized(self):
        """Test that encoding aliases are properly normalized"""
        html = "Test"
        
        # Test various representations of windows-1251
        test_cases = [
            ('windows-1251', 'windows-1251'),
            ('windows_1251', 'windows-1251'),
            ('WINDOWS-1251', 'windows-1251'),
            ('cp1251', 'windows-1251'),
        ]
        
        for detected, expected_norm in test_cases:
            # If encodings match after normalization, should return as-is
            result = fix_html_encoding(html, detected_encoding=detected, transport_encoding=expected_norm)
            self.assertEqual(result, html)

    def test_invalid_encoding_returns_original(self):
        """Test that invalid encoding returns original HTML"""
        html = "Test content"
        result = fix_html_encoding(html, detected_encoding='invalid-encoding', transport_encoding='utf-8')
        self.assertEqual(result, html)

    def test_unicode_error_returns_original(self):
        """Test that Unicode errors return original HTML"""
        # Text with characters that can't be encoded in latin1
        html = "Test 你好 content"
        result = fix_html_encoding(html, detected_encoding='windows-1251', transport_encoding='utf-8')
        # Should return original because encoding to latin1 will fail
        self.assertEqual(result, html)

    def test_iso_8859_1_encoding(self):
        """Test ISO-8859-1 encoding fix"""
        # ISO-8859-1 character "é" (0xE9) incorrectly decoded as UTF-8/latin1
        incorrectly_decoded = "café"
        
        result = fix_html_encoding(
            incorrectly_decoded,
            detected_encoding='iso-8859-1',
            transport_encoding='utf-8'
        )
        
        # Should still be "café" because it's already latin1-compatible
        self.assertEqual(result, "café")

    def test_already_correct_text_not_broken(self):
        """Test that correctly decoded text is not broken"""
        # Properly decoded Cyrillic text
        html = "Цена продукта"
        
        # If we detect windows-1251 but text is already correct
        # Our safety check (matching encodings) should prevent corruption
        result = fix_html_encoding(html, detected_encoding='windows-1251', transport_encoding='windows-1251')
        self.assertEqual(result, html)

    def test_empty_string(self):
        """Test empty string handling"""
        result = fix_html_encoding('', detected_encoding='windows-1251')
        self.assertEqual(result, '')

    def test_mixed_content(self):
        """Test HTML with mixed ASCII and encoded characters"""
        # Mix of ASCII and incorrectly decoded windows-1251
        incorrectly_decoded = '<html><head><title>Öåíà</title></head></html>'
        
        result = fix_html_encoding(
            incorrectly_decoded,
            detected_encoding='windows-1251',
            transport_encoding='utf-8'
        )
        
        # ASCII parts should be unchanged, Cyrillic should be fixed
        self.assertIn('<html>', result)
        self.assertIn('Цена', result)

    def test_transport_encoding_priority(self):
        """Test that transport encoding takes priority over detected"""
        html = "Test"
        
        # Even though detected says windows-1251, if transport says windows-1251 too, no fix
        result = fix_html_encoding(
            html,
            detected_encoding='windows-1251',
            transport_encoding='windows-1251'
        )
        self.assertEqual(result, html)


class TestMojibakeDetection(unittest.TestCase):
    """Test cases for lightweight mojibake detection"""

    def test_clean_utf8_text(self):
        """Test that clean UTF-8 text is not flagged as mojibake"""
        text = "Hello world! This is clean English text."
        result = _has_mojibake_patterns(text)
        self.assertFalse(result)

    def test_clean_cyrillic_text(self):
        """Test that properly decoded Cyrillic is not flagged"""
        text = "Цена продукта составляет 100 рублей"
        result = _has_mojibake_patterns(text)
        self.assertFalse(result)

    def test_windows_1251_mojibake(self):
        """Test detection of windows-1251 decoded as UTF-8"""
        # Simulated mojibake: Cyrillic "Цена" incorrectly decoded
        text = "Öåíà ïðîäóêòà"  # This is mojibake
        result = _has_mojibake_patterns(text)
        self.assertTrue(result)

    def test_double_encoded_utf8(self):
        """Test detection of UTF-8 double encoding"""
        text = "CafÃ© avec du thÃ©"  # Double encoded
        result = _has_mojibake_patterns(text)
        self.assertTrue(result)

    def test_single_mojibake_character_not_flagged(self):
        """Test that single occurrence is not flagged (might be legitimate)"""
        text = "Hello Ð world"  # Just one character
        result = _has_mojibake_patterns(text)
        # Should be False because threshold is 2+
        self.assertFalse(result)

    def test_multiple_mojibake_patterns(self):
        """Test that multiple patterns trigger detection"""
        text = "Ð Ñ Ò Ó product description"
        result = _has_mojibake_patterns(text)
        self.assertTrue(result)

    def test_empty_text(self):
        """Test empty text handling"""
        result = _has_mojibake_patterns("")
        self.assertFalse(result)

    def test_short_text(self):
        """Test very short text"""
        result = _has_mojibake_patterns("Hi")
        self.assertFalse(result)

    def test_html_with_mojibake(self):
        """Test mojibake detection in HTML context"""
        html = "<html><body>Öåíà: 100 Ñ€ÑƒÐ±.</body></html>"
        result = _has_mojibake_patterns(html)
        self.assertTrue(result)


class TestShouldDetectEncoding(unittest.TestCase):
    """Test cases for should_detect_encoding decision logic"""

    def test_no_encoding_provided(self):
        """Test that detection is triggered when no encoding provided"""
        text = "<html><body>Test</body></html>"
        result = should_detect_encoding(text, None)
        self.assertTrue(result)

    def test_encoding_provided_clean_text(self):
        """Test fast path: encoding provided and text looks clean"""
        text = "<html><body>Hello world</body></html>"
        result = should_detect_encoding(text, 'utf-8')
        self.assertFalse(result)

    def test_encoding_provided_mojibake_text(self):
        """Test slow path: encoding provided but text looks corrupted"""
        text = "<html><body>Öåíà ïðîäóêòà</body></html>"
        result = should_detect_encoding(text, 'utf-8')
        self.assertTrue(result)

    def test_empty_text(self):
        """Test empty text returns False"""
        result = should_detect_encoding("", 'utf-8')
        self.assertFalse(result)

    def test_encoding_provided_cyrillic_clean(self):
        """Test that clean Cyrillic with encoding doesn't trigger detection"""
        text = "<html><body>Цена продукта</body></html>"
        result = should_detect_encoding(text, 'utf-8')
        self.assertFalse(result)

    def test_no_encoding_triggers_detection(self):
        """Test that missing encoding always triggers detection"""
        text = "<html><body>Any content</body></html>"
        result = should_detect_encoding(text, None)
        self.assertTrue(result)


class TestEncodingIntegration(unittest.TestCase):
    """Integration tests for encoding detection and fixing"""

    def test_full_workflow_windows_1251(self):
        """Test complete workflow: detect + fix for windows-1251 page"""
        # HTML with windows-1251 meta tag and incorrectly decoded content
        html = '''<html>
        <head>
            <meta http-equiv="Content-Type" content="text/html; charset=windows-1251">
            <title>Öåíà</title>
        </head>
        <body>Öåíà ïðîäóêòà</body>
        </html>'''
        
        # Detect encoding
        detected = detect_html_encoding(html)
        self.assertEqual(detected, 'windows-1251')
        
        # Fix encoding (simulating UTF-8 transport)
        fixed = fix_html_encoding(html, detected_encoding=detected, transport_encoding='utf-8')
        
        # Should have fixed Cyrillic text
        self.assertIn('Цена', fixed)

    def test_full_workflow_correct_encoding(self):
        """Test workflow when encoding is already correct"""
        # Properly decoded UTF-8 HTML
        html = '''<html>
        <head>
            <meta charset="utf-8">
            <title>Цена</title>
        </head>
        <body>Цена продукта</body>
        </html>'''
        
        # Detect encoding
        detected = detect_html_encoding(html)
        self.assertEqual(detected, 'utf-8')
        
        # Fix encoding (with matching transport encoding)
        fixed = fix_html_encoding(html, detected_encoding=detected, transport_encoding='utf-8')
        
        # Should be unchanged
        self.assertEqual(fixed, html)

    def test_full_workflow_no_meta_tag(self):
        """Test workflow when no meta tag present"""
        html = '<html><head><title>Test</title></head><body>Content</body></html>'
        
        # Detect encoding
        detected = detect_html_encoding(html)
        self.assertIsNone(detected)
        
        # Fix encoding (should return as-is)
        fixed = fix_html_encoding(html, detected_encoding=detected)
        self.assertEqual(fixed, html)


if __name__ == '__main__':
    unittest.main()
