#!/usr/bin/env python3
"""
OpenVINO Model Server for DeepSeek-R1-Distill-Qwen-7B-int4-cw-ov
"""

import json
import time
from typing import Dict, Any, List
from flask import Flask, request, jsonify
from openvino_genai import LLMPipeline
import argparse
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

class OpenVINOModelServer:
    def __init__(self, model_path: str, device: str = "CPU"):
        self.model_path = model_path
        self.device = device
        self.model = None
        self.load_model()
    
    def load_model(self):
        """Load the OpenVINO model"""
        try:
            logger.info(f"Loading model from {self.model_path}")
            
            # Configure device-specific properties
            if self.device == "GPU":
                # GPU-specific configuration for better performance
                config = {
                    "CACHE_DIR": "/tmp/openvino_cache",
                    "PERFORMANCE_HINT": "THROUGHPUT"
                }
                logger.info("Using GPU with performance optimizations")
            else:
                config = {}
                logger.info(f"Using {self.device}")
            
            self.model = LLMPipeline(
                models_path=self.model_path, 
                device=self.device,
                **config
            )
            logger.info("Model loaded successfully!")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise
    
    def generate(self, prompt: str, max_tokens: int = 100, temperature: float = 0.7) -> Dict[str, Any]:
        """Generate text using the model"""
        try:
            start_time = time.time()
            
            # Generate response using LLMPipeline with correct API
            response = self.model.generate(
                inputs=prompt,
                max_new_tokens=max_tokens,
                temperature=temperature
            )
            
            generation_time = time.time() - start_time
            
            # Extract the generated text from the response
            generated_text = response if isinstance(response, str) else str(response)
            
            return {
                "response": generated_text,
                "generation_time": generation_time,
                "tokens_generated": len(generated_text.split()),
                "tokens_per_second": len(generated_text.split()) / generation_time if generation_time > 0 else 0
            }
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            return {"error": str(e)}

# Global model server instance
model_server = None

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "model_loaded": model_server is not None})

@app.route('/generate', methods=['POST'])
def generate_text():
    """Generate text endpoint"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        prompt = data.get('prompt', '')
        max_tokens = data.get('max_tokens', 100)
        temperature = data.get('temperature', 0.7)
        
        if not prompt:
            return jsonify({"error": "No prompt provided"}), 400
        
        if model_server is None:
            return jsonify({"error": "Model not loaded"}), 500
        
        result = model_server.generate(prompt, max_tokens, temperature)
        
        return jsonify(result)
    
    except Exception as e:
        logger.error(f"Error in generate_text: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/model_info', methods=['GET'])
def model_info():
    """Get model information"""
    if model_server is None:
        return jsonify({"error": "Model not loaded"}), 500
    
    return jsonify({
        "model_path": model_server.model_path,
        "device": model_server.device,
        "status": "loaded"
    })

@app.route('/', methods=['GET'])
def index():
    """Simple test endpoint"""
    return jsonify({
        "message": "OpenVINO Model Server",
        "endpoints": {
            "health": "/health",
            "generate": "/generate (POST)",
            "model_info": "/model_info"
        },
        "example_usage": {
            "curl": "curl -X POST http://localhost:5000/generate -H 'Content-Type: application/json' -d '{\"prompt\": \"Hello, how are you?\", \"max_tokens\": 50}'"
        }
    })

def main():
    parser = argparse.ArgumentParser(description='OpenVINO Model Server')
    parser.add_argument('--model-path', type=str, default='/home/keithcu/model_path',
                       help='Path to the OpenVINO model')
    parser.add_argument('--device', type=str, default='CPU',
                       help='Device to run on (CPU, GPU, etc.)')
    parser.add_argument('--port', type=int, default=5000,
                       help='Port to run the server on')
    parser.add_argument('--host', type=str, default='0.0.0.0',
                       help='Host to bind to')
    
    args = parser.parse_args()
    
    global model_server
    
    try:
        # Initialize model server
        model_server = OpenVINOModelServer(args.model_path, args.device)
        
        logger.info(f"Starting OpenVINO Model Server on {args.host}:{args.port}")
        logger.info(f"Model path: {args.model_path}")
        logger.info(f"Device: {args.device}")
        
        # Start Flask server
        app.run(host=args.host, port=args.port, debug=False)
        
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        return 1
    
    return 0

if __name__ == '__main__':
    exit(main())
