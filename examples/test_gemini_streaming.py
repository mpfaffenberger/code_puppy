#!/usr/bin/env python3
"""Standalone script to test Gemini streaming from the local puppy-backend.

Usage:
    uv run python examples/test_gemini_streaming.py
"""

import configparser
import httpx
import sys
from pathlib import Path


def load_puppy_token() -> str:
    """Load the puppy_token from ~/.code_puppy/puppy.cfg"""
    config_path = Path.home() / ".code_puppy" / "puppy.cfg"
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    
    config = configparser.ConfigParser()
    config.read(config_path)
    
    token = config.get("puppy", "puppy_token", fallback=None)
    if not token:
        raise ValueError("puppy_token not found in config")
    
    return token


def test_gemini_streaming():
    """Make a streaming request to the local backend for Gemini."""
    token = load_puppy_token()
    
    # Gemini streaming uses streamGenerateContent in the URL
    model = "gemini-3-pro-preview"
    # Note: pydantic-ai adds ?alt=sse, but let's test with what our backend returns
    url = f"http://localhost:8080/gemini/v1beta1/publishers/google/models/{model}:streamGenerateContent?alt=sse"
    
    # Gemini native API format
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": "Count from 1 to 3."}]
            }
        ],
        "generationConfig": {
            "maxOutputTokens": 200,
            "temperature": 0.7
        }
    }
    
    headers = {
        "X-Goog-Api-Key": token,
        "Content-Type": "application/json",
    }
    
    print(f">> Sending Gemini streaming request to {url}")
    print(f">> Model: {model}")
    print("-" * 60)
    print(">> Raw bytes (showing first 500 chars of each chunk):")
    print("-" * 60)
    
    chunk_count = 0
    
    with httpx.Client(timeout=60.0) as client:
        with client.stream("POST", url, json=payload, headers=headers) as response:
            print(f"Status: {response.status_code}")
            print(f"Content-Type: {response.headers.get('content-type')}")
            print("-" * 60)
            
            if response.status_code != 200:
                print(f"Error: {response.read().decode()}")
                return
            
            # Read raw bytes to see exactly what's coming
            for chunk in response.iter_bytes():
                chunk_count += 1
                chunk_str = chunk.decode('utf-8', errors='replace')
                # Show first 500 chars and repr to see exact format
                print(f"[CHUNK {chunk_count:03d}] repr: {repr(chunk_str[:200])}")
                sys.stdout.flush()
    
    print("-" * 60)
    print(f"Done! Received {chunk_count} byte chunks.")


if __name__ == "__main__":
    try:
        test_gemini_streaming()
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"Error: {e}")
        raise
