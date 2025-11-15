#!/bin/bash
# Script to install CPU-only ML dependencies
# Install CPU PyTorch first to prevent GPU versions from being pulled in

set -e  # Exit on any error

echo "Installing CPU PyTorch packages..."
uv pip install --index https://download.pytorch.org/whl/cpu torch torchvision torchaudio

echo "Installing sentence_transformers (will use CPU PyTorch)..."
uv pip install sentence_transformers

echo "CPU ML dependencies installed successfully!"
echo "PyTorch version: $(uv run python -c 'import torch; print(torch.__version__)')"
echo "CUDA available: $(uv run python -c 'import torch; print(torch.cuda.is_available())')"
