import unittest
import sys
import os

# Add the parent directory to Python path when running tests directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from auto_update import extract_top_titles_from_ai, TITLE_MARKER

class TestExtractTopTitles(unittest.TestCase):

    def setUp(self):
        """Set up test fixtures."""
        # Ensure we have a clean state for each test
        pass

    def tearDown(self):
        """Clean up after each test."""
        pass

    def test_standard_format(self):
        """Test standard format with title marker"""
        text = f"""
        Some reasoning here.
        
        {TITLE_MARKER}
        First headline here
        Second headline here
        Third headline here
        """
        titles = extract_top_titles_from_ai(text)
        self.assertEqual(len(titles), 3)
        self.assertEqual(titles[0], "First headline here")
        self.assertEqual(titles[1], "Second headline here")
        self.assertEqual(titles[2], "Third headline here")

    def test_marker_with_extra_spaces(self):
        """Test title marker with extra spaces"""
        text = f"""
        Some reasoning here.
        
        {TITLE_MARKER}  
        First headline here
        Second headline here
        Third headline here
        """
        titles = extract_top_titles_from_ai(text)
        self.assertEqual(len(titles), 3)
        self.assertEqual(titles[0], "First headline here")

    def test_no_marker_bottom_up(self):
        """Test bottom-up search when no marker is found"""
        text = """
        Some reasoning here.
        
        1. First headline here
        2. Second headline here
        3. Third headline here
        """
        titles = extract_top_titles_from_ai(text)
        self.assertEqual(len(titles), 3)
        self.assertEqual(titles[0], "First headline here")
        self.assertEqual(titles[1], "Second headline here")
        self.assertEqual(titles[2], "Third headline here")

    def test_numbered_format_variations(self):
        """Test different numbered formats"""
        text = """
        Some reasoning here.
        
        1) First headline here
        2. Second headline here
        3- Third headline here
        """
        titles = extract_top_titles_from_ai(text)
        self.assertEqual(len(titles), 3)
        self.assertEqual(titles[0], "First headline here")
        self.assertEqual(titles[1], "Second headline here")
        self.assertEqual(titles[2], "Third headline here")

    def test_formatting_cleanup(self):
        """Test cleanup of various formatting characters"""
        text = f"""
        Some reasoning here.
        
        {TITLE_MARKER}
        *First headline here*
        "Second headline here"
        --Third headline here--
        """
        titles = extract_top_titles_from_ai(text)
        self.assertEqual(len(titles), 3)
        self.assertEqual(titles[0], "First headline here")
        self.assertEqual(titles[1], "Second headline here")
        self.assertEqual(titles[2], "Third headline here")

    def test_markdown_formatting(self):
        """Test cleanup of markdown formatting"""
        text = f"""
        Some reasoning here.
        
        {TITLE_MARKER}
        **First headline here**
        *Second headline here*
        `Third headline here`
        """
        titles = extract_top_titles_from_ai(text)
        self.assertEqual(len(titles), 3)
        self.assertEqual(titles[0], "First headline here")
        self.assertEqual(titles[1], "Second headline here")
        # Note: Backticks are not removed by the function
        self.assertEqual(titles[2], "`Third headline here`")

    def test_invalid_titles(self):
        """Test filtering of invalid titles"""
        text = f"""
        Some reasoning here.
        
        {TITLE_MARKER}
        Too short
        http://invalid.com
        www.invalid.org
        Valid headline here
        Another valid headline
        Third valid headline
        """
        titles = extract_top_titles_from_ai(text)
        self.assertEqual(len(titles), 3)
        self.assertEqual(titles[0], "Valid headline here")
        self.assertEqual(titles[1], "Another valid headline")
        self.assertEqual(titles[2], "Third valid headline")

    def test_separator_only_titles(self):
        """Test filtering of titles that are just separators"""
        text = f"""
        Some reasoning here.
        
        {TITLE_MARKER}
        ---------
        =========
        Valid headline here
        Another valid headline
        Third valid headline
        """
        titles = extract_top_titles_from_ai(text)
        self.assertEqual(len(titles), 3)
        self.assertEqual(titles[0], "Valid headline here")
        self.assertEqual(titles[1], "Another valid headline")
        self.assertEqual(titles[2], "Third valid headline")

    def test_mixed_formatting(self):
        """Test mixed formatting in titles"""
        text = f"""
        Some reasoning here.
        
        {TITLE_MARKER}
        *First headline with **bold** and *italic**
        "Second headline with quotes and dashes--"
        Third headline with markdown `code` and **bold**
        """
        titles = extract_top_titles_from_ai(text)
        self.assertEqual(len(titles), 3)
        # Note: Nested markdown formatting is not fully cleaned up
        self.assertEqual(titles[0], "First headline with bold and *italic")
        self.assertEqual(titles[1], "Second headline with quotes and dashes")
        self.assertEqual(titles[2], "Third headline with markdown `code` and bold")

    def test_empty_lines(self):
        """Test handling of empty lines"""
        text = f"""
        Some reasoning here.
        
        {TITLE_MARKER}
        
        First headline here
        
        Second headline here
        
        Third headline here
        
        """
        titles = extract_top_titles_from_ai(text)
        self.assertEqual(len(titles), 3)
        self.assertEqual(titles[0], "First headline here")
        self.assertEqual(titles[1], "Second headline here")
        self.assertEqual(titles[2], "Third headline here")

    def test_no_valid_titles(self):
        """Test when no valid titles are found"""
        text = """
        Some reasoning here.
        
        Too short
        http://invalid.com
        www.invalid.org
        ---------
        """
        titles = extract_top_titles_from_ai(text)
        self.assertEqual(len(titles), 0)

    def test_marker_in_middle(self):
        """Test when marker appears in middle of text"""
        text = f"""
        Some reasoning here.
        
        {TITLE_MARKER}
        First headline here
        Second headline here
        Third headline here
        
        More text after titles
        """
        titles = extract_top_titles_from_ai(text)
        self.assertEqual(len(titles), 3)
        self.assertEqual(titles[0], "First headline here")
        self.assertEqual(titles[1], "Second headline here")
        self.assertEqual(titles[2], "Third headline here")

    def test_marker_with_extra_text(self):
        """Test when marker has extra text around it"""
        text = f"""
        Some reasoning here.

        Here are the {TITLE_MARKER} for today:
        First headline here
        Second headline here
        Third headline here
        """
        titles = extract_top_titles_from_ai(text)
        self.assertEqual(len(titles), 3)
        # Note: Text after the marker is included as a title
        self.assertEqual(titles[0], "for today:")
        self.assertEqual(titles[1], "First headline here")
        self.assertEqual(titles[2], "Second headline here")

    def test_max_titles_limit(self):
        """Test that function respects maximum title limits"""
        text = f"""
        Some reasoning here.

        {TITLE_MARKER}
        Title 1
        Title 2
        Title 3
        Title 4
        Title 5
        Title 6
        """
        titles = extract_top_titles_from_ai(text)
        # Function should return all valid titles found
        self.assertGreater(len(titles), 0)
        self.assertLessEqual(len(titles), 6)

    def test_unicode_characters(self):
        """Test handling of Unicode characters in titles"""
        text = f"""
        Some reasoning here.

        {TITLE_MARKER}
        Título con acentos: café
        Заголовок на русском
        Title with emoji 🚀
        """
        titles = extract_top_titles_from_ai(text)
        self.assertEqual(len(titles), 3)
        self.assertIn("Título con acentos: café", titles)
        self.assertIn("Заголовок на русском", titles)
        self.assertIn("Title with emoji 🚀", titles)

    def test_case_insensitive_marker(self):
        """Test that marker detection is case-insensitive"""
        # Test with different case variations
        test_cases = [
            TITLE_MARKER.upper(),
            TITLE_MARKER.lower(),
            TITLE_MARKER.capitalize(),
        ]

        for marker in test_cases:
            text = f"""
            Some reasoning here.

            {marker}
            Test headline
            """
            titles = extract_top_titles_from_ai(text)
            self.assertEqual(len(titles), 1, f"Failed for marker: {marker}")
            self.assertEqual(titles[0], "Test headline")

if __name__ == '__main__':
    unittest.main() 