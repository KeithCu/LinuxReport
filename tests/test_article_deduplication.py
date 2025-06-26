#!/usr/bin/env python3
"""
Comprehensive tests for article deduplication functionality.

Tests the embedding-based deduplication system with various edge cases including:
- Similar titles with minor differences (numbers, punctuation, spacing)
- Empty/invalid inputs
- Edge cases that could cause negative similarity scores
- Cache behavior
- Threshold testing
- Error handling and robustness
"""

import unittest
import sys
import os
import tempfile
import json
import warnings

# Add the parent directory to the path so we can import the modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from article_deduplication import (
    get_embedding, 
    deduplicate_articles_with_exclusions, 
    get_best_matching_article,
    clamp_similarity,
    THRESHOLD
)


class TestArticleDeduplication(unittest.TestCase):
    """Test cases for article deduplication functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Clear any existing embedding cache to ensure clean tests
        from article_deduplication import embedding_cache
        embedding_cache.clear()
        
        # Test articles with various similarity patterns
        self.test_articles = [
            {"title": "Trump Delivers Victory in 12-Day War", "url": "https://example.com/1"},
            {"title": "Trump Delivers Victory in 12 Day War", "url": "https://example.com/2"},  # No hyphen
            {"title": "Trump Delivers Victory in 12 Day War!", "url": "https://example.com/3"},  # With exclamation
            {"title": "Trump Delivers Victory in 12-Day War", "url": "https://example.com/4"},  # Exact duplicate
            {"title": "Biden Announces New Economic Policy", "url": "https://example.com/5"},  # Different topic
            {"title": "Trump Announces New Economic Policy", "url": "https://example.com/6"},  # Similar but different
            {"title": "12-Day War Victory Delivered by Trump", "url": "https://example.com/7"},  # Reordered words
            {"title": "Trump's 12-Day War Victory", "url": "https://example.com/8"},  # Abbreviated version
            {"title": "The 12-Day War: Trump's Victory", "url": "https://example.com/9"},  # Different format
            {"title": "Trump Wins 12-Day War", "url": "https://example.com/10"},  # Synonym usage
            {"title": "Trump Triumphs in 12-Day War", "url": "https://example.com/11"},  # Different verb
            {"title": "12 Day War Victory: Trump Delivers", "url": "https://example.com/12"},  # Colon format
            {"title": "Trump Delivers Victory in 12-Day War", "url": "https://example.com/13"},  # Another exact duplicate
            {"title": "Breaking: Trump Delivers Victory in 12-Day War", "url": "https://example.com/14"},  # With "Breaking:"
            {"title": "Trump Delivers Victory in 12-Day War - Latest News", "url": "https://example.com/15"},  # With suffix
            {"title": "TRUMP DELIVERS VICTORY IN 12-DAY WAR", "url": "https://example.com/16"},  # All caps
            {"title": "trump delivers victory in 12-day war", "url": "https://example.com/17"},  # All lowercase
            {"title": "Trump Delivers Victory in 12-Day War", "url": "https://example.com/18"},  # Another exact duplicate
        ]
        
        # Edge case articles
        self.edge_case_articles = [
            {"title": "", "url": "https://example.com/empty"},  # Empty title
            {"title": "   ", "url": "https://example.com/whitespace"},  # Whitespace only
            {"title": "A", "url": "https://example.com/single_char"},  # Single character
            {"title": "123", "url": "https://example.com/numbers_only"},  # Numbers only
            {"title": "!@#$%^&*()", "url": "https://example.com/symbols_only"},  # Symbols only
            {"title": "Trump Delivers Victory in 12-Day War" * 10, "url": "https://example.com/very_long"},  # Very long
            {"title": None, "url": "https://example.com/none"},  # None title (should be handled gracefully)
        ]
        
        # Malformed articles for testing error handling
        self.malformed_articles = [
            None,  # Not a dict
            {},  # Empty dict
            {"url": "https://example.com/no_title"},  # Missing title
            {"title": None, "url": "https://example.com/none_title"},  # None title
            {"title": 123, "url": "https://example.com/numeric_title"},  # Non-string title
            {"title": "", "url": "https://example.com/empty_title"},  # Empty title
            {"title": "   ", "url": "https://example.com/whitespace_title"},  # Whitespace title
        ]

    def test_clamp_similarity_robustness(self):
        """Test that clamp_similarity handles various input types robustly."""
        # Test normal cases
        self.assertEqual(clamp_similarity(0.5), 0.5)
        self.assertEqual(clamp_similarity(-0.5), -0.5)
        self.assertEqual(clamp_similarity(1.0), 1.0)
        self.assertEqual(clamp_similarity(-1.0), -1.0)
        
        # Test clamping
        self.assertEqual(clamp_similarity(1.5), 1.0)
        self.assertEqual(clamp_similarity(-1.5), -1.0)
        self.assertEqual(clamp_similarity(2.0), 1.0)
        self.assertEqual(clamp_similarity(-2.0), -1.0)
        
        # Test edge cases
        self.assertEqual(clamp_similarity(0.0), 0.0)
        self.assertEqual(clamp_similarity(float('inf')), 1.0)
        self.assertEqual(clamp_similarity(float('-inf')), -1.0)
        self.assertEqual(clamp_similarity(float('nan')), 0.0)  # NaN becomes 0.0
        
        # Test non-numeric inputs
        with warnings.catch_warnings(record=True) as w:
            self.assertEqual(clamp_similarity("not a number"), 0.0)
            self.assertEqual(clamp_similarity(None), 0.0)
            self.assertEqual(clamp_similarity([]), 0.0)
            self.assertEqual(len(w), 3)  # Should have 3 warnings

    def test_get_embedding_robustness(self):
        """Test that get_embedding handles various input types robustly."""
        # Test normal cases
        emb1 = get_embedding("Normal text")
        self.assertIsNotNone(emb1)
        self.assertTrue(hasattr(emb1, 'tolist'))
        
        # Test edge cases
        emb2 = get_embedding("")  # Empty string
        self.assertIsNotNone(emb2)
        
        emb3 = get_embedding("   ")  # Whitespace only
        self.assertIsNotNone(emb3)
        
        emb4 = get_embedding(None)  # None
        self.assertIsNotNone(emb4)
        
        # Test non-string inputs
        with warnings.catch_warnings(record=True) as w:
            emb5 = get_embedding(123)  # Integer
            self.assertIsNotNone(emb5)
            
            emb6 = get_embedding(["list"])  # List
            self.assertIsNotNone(emb6)
            
            self.assertGreater(len(w), 0)  # Should have warnings

    def test_deduplication_with_malformed_input(self):
        """Test deduplication with malformed input data."""
        # Test with malformed articles
        excluded_embeddings = []
        
        with warnings.catch_warnings(record=True) as w:
            result = deduplicate_articles_with_exclusions(self.malformed_articles, excluded_embeddings)
            
            # Should handle malformed input gracefully
            self.assertIsInstance(result, list)
            self.assertEqual(len(result), 0)  # All malformed articles should be filtered out
            
            # Should have warnings for malformed input
            self.assertGreater(len(w), 0)

    def test_deduplication_with_invalid_parameters(self):
        """Test deduplication with invalid parameters."""
        valid_articles = [{"title": "Test Article", "url": "https://example.com/test"}]
        
        # Test with invalid articles parameter
        with warnings.catch_warnings(record=True) as w:
            result = deduplicate_articles_with_exclusions("not a list", [])
            self.assertEqual(result, [])
            self.assertGreater(len(w), 0)
        
        # Test with invalid excluded_embeddings parameter
        with warnings.catch_warnings(record=True) as w:
            result = deduplicate_articles_with_exclusions(valid_articles, "not a list")
            self.assertIsInstance(result, list)
            self.assertGreater(len(w), 0)
        
        # Test with invalid threshold
        with warnings.catch_warnings(record=True) as w:
            result = deduplicate_articles_with_exclusions(valid_articles, [], threshold="invalid")
            self.assertIsInstance(result, list)
            self.assertGreater(len(w), 0)
        
        # Test with threshold out of range
        with warnings.catch_warnings(record=True) as w:
            result = deduplicate_articles_with_exclusions(valid_articles, [], threshold=1.5)
            self.assertIsInstance(result, list)
            self.assertGreater(len(w), 0)

    def test_get_best_matching_article_robustness(self):
        """Test get_best_matching_article with various edge cases."""
        valid_articles = [
            {"title": "Trump Delivers Victory in 12-Day War", "url": "https://example.com/1"},
            {"title": "Biden Announces New Economic Policy", "url": "https://example.com/2"},
        ]
        
        # Test with invalid target_title
        with warnings.catch_warnings(record=True) as w:
            result = get_best_matching_article(None, valid_articles)
            self.assertIsNone(result)
            self.assertGreater(len(w), 0)
        
        with warnings.catch_warnings(record=True) as w:
            result = get_best_matching_article("", valid_articles)
            self.assertIsNone(result)
            self.assertGreater(len(w), 0)
        
        with warnings.catch_warnings(record=True) as w:
            result = get_best_matching_article("   ", valid_articles)
            self.assertIsNone(result)
            self.assertGreater(len(w), 0)
        
        # Test with invalid articles parameter
        with warnings.catch_warnings(record=True) as w:
            result = get_best_matching_article("Test", "not a list")
            self.assertIsNone(result)
            self.assertGreater(len(w), 0)
        
        # Test with empty articles list
        result = get_best_matching_article("Test", [])
        self.assertIsNone(result)
        
        # Test with malformed articles
        malformed_articles = [{"url": "no title"}, None, "not a dict"]
        with warnings.catch_warnings(record=True) as w:
            result = get_best_matching_article("Test", malformed_articles)
            self.assertIsNone(result)
            self.assertGreater(len(w), 0)

    def test_stress_test_large_dataset(self):
        """Test with a large dataset to check for performance and memory issues."""
        # Create a large dataset
        large_articles = []
        for i in range(1000):
            large_articles.append({
                "title": f"Article {i}: Trump Delivers Victory in {i}-Day War",
                "url": f"https://example.com/{i}"
            })
        
        # Add some duplicates
        large_articles.extend([
            {"title": "Trump Delivers Victory in 12-Day War", "url": "https://example.com/duplicate1"},
            {"title": "Trump Delivers Victory in 12 Day War", "url": "https://example.com/duplicate2"},
        ])
        
        excluded_embeddings = []
        
        # This should not crash or take too long
        import time
        start_time = time.time()
        
        result = deduplicate_articles_with_exclusions(large_articles, excluded_embeddings)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Should complete in reasonable time (less than 30 seconds)
        self.assertLess(processing_time, 30.0, f"Processing took too long: {processing_time:.2f} seconds")
        
        # Should have filtered out duplicates
        titles = [art["title"] for art in result]
        self.assertLess(len(result), len(large_articles))
        
        # Check for duplicates in result
        duplicates = [title for title in set(titles) if titles.count(title) > 1]
        self.assertEqual(len(duplicates), 0, f"Found duplicates in result: {duplicates}")

    def test_memory_usage(self):
        """Test that memory usage doesn't grow excessively."""
        import gc
        import psutil
        import os
        
        # Get initial memory usage
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss
        
        # Process multiple batches
        for batch in range(5):
            articles = [
                {"title": f"Article {i} in batch {batch}", "url": f"https://example.com/{batch}/{i}"}
                for i in range(100)
            ]
            
            result = deduplicate_articles_with_exclusions(articles, [])
            
            # Force garbage collection
            gc.collect()
        
        # Get final memory usage
        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory
        
        # Memory increase should be reasonable (less than 100MB)
        self.assertLess(memory_increase, 100 * 1024 * 1024, 
                       f"Memory usage increased too much: {memory_increase / (1024*1024):.2f} MB")

    def test_concurrent_access(self):
        """Test that the functions can handle concurrent access safely."""
        import threading
        import time
        
        results = []
        errors = []
        
        def worker(worker_id):
            try:
                articles = [
                    {"title": f"Worker {worker_id} Article {i}", "url": f"https://example.com/w{worker_id}/{i}"}
                    for i in range(10)
                ]
                result = deduplicate_articles_with_exclusions(articles, [])
                results.append((worker_id, len(result)))
            except Exception as e:
                errors.append((worker_id, str(e)))
        
        # Start multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Check that no errors occurred
        self.assertEqual(len(errors), 0, f"Errors occurred in concurrent access: {errors}")
        
        # Check that all workers completed successfully
        self.assertEqual(len(results), 5)
        for worker_id, result_count in results:
            self.assertGreaterEqual(result_count, 0)

    def test_cache_consistency(self):
        """Test that the embedding cache works correctly under various conditions."""
        from article_deduplication import embedding_cache
        
        # Clear cache
        embedding_cache.clear()
        
        # Test basic caching
        text = "Test text for caching"
        emb1 = get_embedding(text)
        emb2 = get_embedding(text)
        self.assertIs(emb1, emb2)  # Should be the same object
        self.assertIn(text, embedding_cache)
        
        # Test cache with edge cases
        edge_texts = ["", "   ", None, 123]
        for text in edge_texts:
            emb = get_embedding(text)
            self.assertIsNotNone(emb)
        
        # Test cache size doesn't grow excessively
        cache_size = len(embedding_cache)
        self.assertLess(cache_size, 1000, f"Cache size too large: {cache_size}")

    def test_threshold_edge_cases(self):
        """Test threshold behavior at the edges."""
        articles = [
            {"title": "Trump Delivers Victory in 12-Day War", "url": "https://example.com/1"},
            {"title": "Trump Delivers Victory in 12 Day War", "url": "https://example.com/2"},
        ]
        
        excluded_embeddings = []
        
        # Test with very low threshold
        result_low = deduplicate_articles_with_exclusions(articles, excluded_embeddings, threshold=0.0)
        self.assertEqual(len(result_low), 1)  # Should filter out similar articles
        
        # Test with very high threshold
        result_high = deduplicate_articles_with_exclusions(articles, excluded_embeddings, threshold=0.99)
        # At high threshold, only one article should remain because the two are still similar
        self.assertEqual(len(result_high), 1)
        
        # Test with exactly 1.0 threshold
        result_exact = deduplicate_articles_with_exclusions(articles, excluded_embeddings, threshold=1.0)
        # At threshold 1.0, both articles are allowed through unless they are exactly identical
        self.assertEqual(len(result_exact), 2)

    def test_embedding_consistency(self):
        """Test that embeddings are consistent for the same text."""
        text = "Trump Delivers Victory in 12-Day War"
        emb1 = get_embedding(text)
        emb2 = get_embedding(text)
        
        # Should be the same tensor (cached)
        self.assertEqual(emb1.tolist(), emb2.tolist())
        
        # Test that different text gives different embeddings
        emb3 = get_embedding("Biden Announces New Economic Policy")
        self.assertNotEqual(emb1.tolist(), emb3.tolist())

    def test_embedding_validity(self):
        """Test that embeddings are valid (not NaN, not all zeros, etc.)."""
        text = "Trump Delivers Victory in 12-Day War"
        embedding = get_embedding(text)
        
        # Should be a tensor
        self.assertTrue(hasattr(embedding, 'tolist'))
        
        # Should not be all zeros
        embedding_list = embedding.tolist()
        self.assertNotEqual(embedding_list, [0.0] * len(embedding_list))
        
        # Should not contain NaN values
        import math
        for val in embedding_list:
            self.assertFalse(math.isnan(val))

    def test_similarity_scores(self):
        """Test that similarity scores are reasonable (between -1 and 1, mostly positive for similar text)."""
        text1 = "Trump Delivers Victory in 12-Day War"
        text2 = "Trump Delivers Victory in 12 Day War"  # Minor difference
        text3 = "Biden Announces New Economic Policy"   # Different topic
        emb1 = get_embedding(text1)
        emb2 = get_embedding(text2)
        emb3 = get_embedding(text3)
        from article_deduplication import st_util, clamp_similarity
        # Similar texts should have high similarity
        sim_similar = clamp_similarity(st_util.cos_sim(emb1, emb2).item())
        self.assertGreaterEqual(sim_similar, 0.8)  # Should be very similar
        self.assertLessEqual(sim_similar, 1.0)
        self.assertGreaterEqual(sim_similar, -1.0)
        # Different texts should have lower similarity
        sim_different = clamp_similarity(st_util.cos_sim(emb1, emb3).item())
        self.assertLess(sim_different, sim_similar)  # Should be less similar
        self.assertGreaterEqual(sim_different, -1.0)
        self.assertLessEqual(sim_different, 1.0)
        # Self-similarity should be 1.0
        sim_self = clamp_similarity(st_util.cos_sim(emb1, emb1).item())
        self.assertAlmostEqual(sim_self, 1.0, places=5)
        self.assertGreaterEqual(sim_self, -1.0)
        self.assertLessEqual(sim_self, 1.0)

    def test_deduplication_basic(self):
        """Test basic deduplication functionality."""
        # Create a list with some duplicates
        articles = [
            {"title": "Trump Delivers Victory in 12-Day War", "url": "https://example.com/1"},
            {"title": "Trump Delivers Victory in 12-Day War", "url": "https://example.com/2"},  # Exact duplicate
            {"title": "Biden Announces New Economic Policy", "url": "https://example.com/3"},
        ]
        
        # No previous selections
        excluded_embeddings = []
        
        result = deduplicate_articles_with_exclusions(articles, excluded_embeddings)
        
        # Should have 2 unique articles (duplicate removed)
        self.assertEqual(len(result), 2)
        
        # Check that the duplicate was removed
        titles = [art["title"] for art in result]
        self.assertIn("Trump Delivers Victory in 12-Day War", titles)
        self.assertIn("Biden Announces New Economic Policy", titles)
        self.assertEqual(titles.count("Trump Delivers Victory in 12-Day War"), 1)

    def test_deduplication_with_previous_selections(self):
        """Test deduplication against previous selections."""
        # Previous selections
        previous_selections = [
            {"title": "Trump Delivers Victory in 12-Day War", "url": "https://example.com/prev1"},
            {"title": "Biden Announces New Economic Policy", "url": "https://example.com/prev2"},
        ]
        
        # Create embeddings for previous selections
        excluded_embeddings = [get_embedding(sel["title"]) for sel in previous_selections]
        
        # New articles (some similar to previous)
        new_articles = [
            {"title": "Trump Delivers Victory in 12 Day War", "url": "https://example.com/new1"},  # Similar to prev1
            {"title": "Biden Announces New Economic Policy", "url": "https://example.com/new2"},  # Exact match to prev2
            {"title": "New Topic: Climate Change", "url": "https://example.com/new3"},  # Different
        ]
        
        result = deduplicate_articles_with_exclusions(new_articles, excluded_embeddings)
        
        # Should filter out articles similar to previous selections
        titles = [art["title"] for art in result]
        self.assertNotIn("Biden Announces New Economic Policy", titles)  # Exact match should be filtered
        self.assertIn("New Topic: Climate Change", titles)  # Different should remain
        
        # The similar one might be filtered depending on threshold
        if "Trump Delivers Victory in 12 Day War" in titles:
            print("Note: Similar title was not filtered - threshold may be too high")

    def test_threshold_behavior(self):
        """Test how different thresholds affect deduplication."""
        articles = [
            {"title": "Trump Delivers Victory in 12-Day War", "url": "https://example.com/1"},
            {"title": "Trump Delivers Victory in 12 Day War", "url": "https://example.com/2"},  # Minor difference
            {"title": "Trump Wins 12-Day War", "url": "https://example.com/3"},  # More different
            {"title": "Biden Announces New Economic Policy", "url": "https://example.com/4"},  # Very different
        ]
        
        excluded_embeddings = []
        
        # Test with different thresholds
        thresholds = [0.5, 0.75, 0.9, 0.95]
        
        for threshold in thresholds:
            result = deduplicate_articles_with_exclusions(articles, excluded_embeddings, threshold)
            print(f"Threshold {threshold}: {len(result)} articles remain")
            
            # Higher threshold should allow more similar articles through
            if threshold == 0.5:
                # Very strict - should filter out most similar articles
                self.assertLessEqual(len(result), 2)
            elif threshold == 0.95:
                # Very lenient - should allow most articles through
                self.assertGreaterEqual(len(result), 3)

    def test_edge_cases(self):
        """Test edge cases that could cause issues."""
        # Test with edge case articles
        excluded_embeddings = []
        
        # This should not crash
        try:
            result = deduplicate_articles_with_exclusions(self.edge_case_articles, excluded_embeddings)
            print(f"Edge cases processed successfully: {len(result)} articles remain")
        except Exception as e:
            self.fail(f"Edge case processing failed: {e}")

    def test_get_best_matching_article(self):
        """Test the get_best_matching_article function."""
        articles = [
            {"title": "Trump Delivers Victory in 12-Day War", "url": "https://example.com/1"},
            {"title": "Trump Delivers Victory in 12 Day War", "url": "https://example.com/2"},
            {"title": "Biden Announces New Economic Policy", "url": "https://example.com/3"},
        ]
        
        # Test exact match
        result = get_best_matching_article("Trump Delivers Victory in 12-Day War", articles)
        self.assertIsNotNone(result)
        self.assertEqual(result["title"], "Trump Delivers Victory in 12-Day War")
        
        # Test similar match
        result = get_best_matching_article("Trump Delivers Victory in 12 Day War", articles)
        self.assertIsNotNone(result)
        self.assertIn(result["title"], ["Trump Delivers Victory in 12-Day War", "Trump Delivers Victory in 12 Day War"])
        
        # Test no match (below threshold)
        result = get_best_matching_article("Completely Different Topic", articles)
        if result is None:
            print("No match found for completely different topic (expected)")
        else:
            print(f"Unexpected match found: {result['title']}")

    def test_cache_behavior(self):
        """Test that the embedding cache works correctly."""
        from article_deduplication import embedding_cache
        
        # Clear cache
        embedding_cache.clear()
        
        # First call should compute embedding
        text = "Test text for caching"
        emb1 = get_embedding(text)
        
        # Second call should use cache
        emb2 = get_embedding(text)
        
        # Should be the same object (cached)
        self.assertIs(emb1, emb2)
        
        # Cache should contain the text
        self.assertIn(text, embedding_cache)

    def test_negative_similarity_bug(self):
        """Test for the negative similarity score bug mentioned by the user."""
        test_cases = [
            ("Trump Delivers Victory in 12-Day War", "Trump Delivers Victory in 12 Day War"),
            ("Breaking: Trump Delivers Victory in 12-Day War", "Trump Delivers Victory in 12-Day War"),
            ("Trump Delivers Victory in 12-Day War!", "Trump Delivers Victory in 12-Day War"),
            ("TRUMP DELIVERS VICTORY IN 12-DAY WAR", "trump delivers victory in 12-day war"),
        ]
        from article_deduplication import st_util, clamp_similarity
        for text1, text2 in test_cases:
            emb1 = get_embedding(text1)
            emb2 = get_embedding(text2)
            similarity = clamp_similarity(st_util.cos_sim(emb1, emb2).item())
            # Similarity should be in [-1, 1]
            self.assertGreaterEqual(similarity, -1.0)
            self.assertLessEqual(similarity, 1.0)
            # For very similar text, similarity should be high
            if text1.lower().replace(" ", "").replace("-", "").replace("!", "") == text2.lower().replace(" ", "").replace("-", "").replace("!", ""):
                self.assertGreater(similarity, 0.8, f"Similarity too low for similar texts: '{text1}' vs '{text2}' = {similarity}")
            # Should not be negative for similar text
            if similarity < 0:
                print(f"WARNING: Negative similarity detected: '{text1}' vs '{text2}' = {similarity}")

    def test_real_world_scenario(self):
        """Test a real-world scenario similar to what the user experienced."""
        # Simulate the user's scenario with Trump war headlines
        previous_selections = [
            {"title": "Trump Delivers Victory in 12-Day War", "url": "https://example.com/prev1"},
        ]
        
        excluded_embeddings = [get_embedding(sel["title"]) for sel in previous_selections]
        
        # New articles that might be selected
        new_articles = [
            {"title": "Trump Delivers Victory in 12 Day War", "url": "https://example.com/new1"},  # No hyphen
            {"title": "Trump Gets Big Praise and New Commitments From NATO", "url": "https://example.com/new2"},
            {"title": "America Will Be Better Off, And More Self-Reliant, Without Illegal Immigrant Labor", "url": "https://example.com/new3"},
        ]
        
        result = deduplicate_articles_with_exclusions(new_articles, excluded_embeddings)
        
        # The similar title should be filtered out
        titles = [art["title"] for art in result]
        self.assertNotIn("Trump Delivers Victory in 12 Day War", titles, 
                        "Similar title should be filtered out to prevent duplicates")
        
        # Other titles should remain
        self.assertIn("Trump Gets Big Praise and New Commitments From NATO", titles)
        self.assertIn("America Will Be Better Off, And More Self-Reliant, Without Illegal Immigrant Labor", titles)


def run_performance_test():
    """Run a performance test to check for any issues with large datasets."""
    print("\n=== Performance Test ===")
    
    # Create a large dataset
    articles = []
    for i in range(100):
        articles.append({
            "title": f"Article {i}: Trump Delivers Victory in {i}-Day War",
            "url": f"https://example.com/{i}"
        })
    
    # Add some duplicates
    articles.extend([
        {"title": "Trump Delivers Victory in 12-Day War", "url": "https://example.com/duplicate1"},
        {"title": "Trump Delivers Victory in 12 Day War", "url": "https://example.com/duplicate2"},
        {"title": "Trump Delivers Victory in 12-Day War", "url": "https://example.com/duplicate3"},
    ])
    
    excluded_embeddings = []
    
    import time
    start_time = time.time()
    
    result = deduplicate_articles_with_exclusions(articles, excluded_embeddings)
    
    end_time = time.time()
    
    print(f"Processed {len(articles)} articles in {end_time - start_time:.2f} seconds")
    print(f"Result: {len(result)} unique articles")
    
    # Check for duplicates in result
    titles = [art["title"] for art in result]
    duplicates = [title for title in set(titles) if titles.count(title) > 1]
    
    if duplicates:
        print(f"WARNING: Duplicates found in result: {duplicates}")
    else:
        print("No duplicates found in result")


if __name__ == "__main__":
    # Run the performance test first
    run_performance_test()
    
    # Run the unit tests
    unittest.main(verbosity=2) 