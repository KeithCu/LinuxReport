#!/usr/bin/env python3
"""
Performance comparison script for OpenVINO vs standard model inference
"""

import time
import requests
import json
from typing import Dict, List

def test_openvino_performance(base_url: str, num_requests: int = 5) -> Dict:
    """Test OpenVINO model performance"""
    print("Testing OpenVINO Model Performance...")
    print("=" * 50)
    
    prompt = "What is the meaning of life?"
    times = []
    tokens_per_second = []
    
    for i in range(num_requests):
        try:
            start_time = time.time()
            
            payload = {
                "prompt": prompt,
                "max_tokens": 100,
                "temperature": 0.7
            }
            
            response = requests.post(
                f"{base_url}/generate",
                json=payload,
                headers={'Content-Type': 'application/json'}
            )
            
            total_time = time.time() - start_time
            
            if response.status_code == 200:
                result = response.json()
                times.append(total_time)
                tokens_per_second.append(result.get('tokens_per_second', 0))
                print(f"Request {i+1}: {total_time:.2f}s "
                      f"(tokens/sec: {result.get('tokens_per_second', 0):.2f})")
            else:
                print(f"Request {i+1}: Failed ({response.status_code})")
                
        except Exception as e:
            print(f"Request {i+1}: Error - {e}")
    
    if times:
        return {
            "avg_time": sum(times) / len(times),
            "min_time": min(times),
            "max_time": max(times),
            "avg_tokens_per_second": sum(tokens_per_second) / len(tokens_per_second) if tokens_per_second else 0,
            "total_requests": len(times)
        }
    return {}

def print_performance_summary(results: Dict):
    """Print performance summary"""
    print("\nOpenVINO Performance Summary:")
    print("=" * 50)
    print(f"Average response time: {results.get('avg_time', 0):.2f}s")
    print(f"Min response time: {results.get('min_time', 0):.2f}s")
    print(f"Max response time: {results.get('max_time', 0):.2f}s")
    print(f"Average tokens/second: {results.get('avg_tokens_per_second', 0):.2f}")
    print(f"Successful requests: {results.get('total_requests', 0)}")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='OpenVINO Performance Test')
    parser.add_argument('--url', type=str, default='http://localhost:5001',
                       help='OpenVINO server URL')
    parser.add_argument('--requests', type=int, default=5,
                       help='Number of requests to test')
    
    args = parser.parse_args()
    
    # Test OpenVINO performance
    results = test_openvino_performance(args.url, args.requests)
    print_performance_summary(results)
    
    print("\nOpenVINO Benefits:")
    print("=" * 50)
    print("✓ Optimized for Intel hardware")
    print("✓ Reduced memory footprint")
    print("✓ Faster inference through graph optimization")
    print("✓ Quantized model (int4) for better performance")
    print("✓ CPU-optimized execution")
    
    print("\nModel Information:")
    print("=" * 50)
    print("Model: DeepSeek-R1-Distill-Qwen-7B-int4-cw-ov")
    print("Optimization: OpenVINO with int4 quantization")
    print("Device: CPU")
    print("Framework: OpenVINO GenAI")

if __name__ == '__main__':
    main()
