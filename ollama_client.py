#!/usr/bin/env python3
"""Command‑line client for Ollama via HTTP.

This script reads prompts from the user, sends them as HTTP requests to a
locally running Ollama server, and prints back the model's response.

Usage:
    python ollama_client.py [model]

If no model is provided, a default of "Phi4-mini" will be used. The script
honors the `OLLAMA_HOST` environment variable (default ``http://127.0.0.1:11434``)
for the server address.

Requirements:
    - A running Ollama server/listening daemon.
    - The ``requests`` package installed (`pip install requests`).

"""

import os
import sys

try:
    import requests
except ImportError:
    sys.exit("The 'requests' library is required. install it with 'pip install requests'.")


DEFAULT_MODEL = "Phi4-mini"


def query_ollama(model: str, prompt: str) -> str:
    """Send a prompt to the local Ollama HTTP server and return the text reply.

    This function constructs a POST request to ``/v1/completions`` using the
    ``OLLAMA_HOST`` environment variable (or the default address). The expected
    response format is similar to the OpenAI-style API.
    """
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    url = host.rstrip("/") + "/v1/completions"
    payload = {"model": model, "prompt": prompt}

    try:
        resp = requests.post(url, json=payload, timeout=3600)
        resp.raise_for_status()
    except requests.RequestException as exc:
        return f"HTTP request failed: {exc}"

    try:
        data = resp.json()
    except ValueError:
        return resp.text

    # Try to extract text from common response shapes
    if isinstance(data, dict):
        # OpenAI-like
        choices = data.get("choices")
        if choices and isinstance(choices, list):
            first = choices[0]
            if isinstance(first, dict):
                return first.get("text", first.get("message", ""))
        # Ollama sometimes returns `output` field
        if "output" in data:
            return data.get("output")
    return str(data)


def query_ollama_chat(model: str, prompt: str) -> str:
    """Send a prompt to the local Ollama HTTP chat endpoint and return the text reply.

    Uses the `/v1/chat` endpoint with a `messages` payload so you can test the
    newer chat-style API. Returns a best-effort string extracted from common
    response shapes.
    """
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    url = host.rstrip("/") + "/api/chat"
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False}

    try:
        resp = requests.post(url, json=payload, timeout=3600)
        resp.raise_for_status()
    except requests.RequestException as exc:
        return f"HTTP request failed: {exc}"

    try:
        data = resp.json()
    except ValueError:
        return resp.text

    # Try to extract text from common response shapes
    if isinstance(data, dict):
        choices = data.get("choices")
        if choices and isinstance(choices, list):
            first = choices[0]
            if isinstance(first, dict):
                # OpenAI-like chat responses
                msg = first.get("message")
                if isinstance(msg, dict):
                    return msg.get("content", "")
                # Some variants use `text` or `delta`
                if "text" in first:
                    return first.get("text")
        # Ollama sometimes returns `output` field
        if "output" in data:
            return data.get("output")
    return str(data)


def main():
    model = DEFAULT_MODEL
    # Usage: python ollama_client.py [model] [endpoint]
    # `endpoint` can be 'chat' (default) or 'completions'
    endpoint = "chat"
    if len(sys.argv) >= 2:
        model = sys.argv[1]
    if len(sys.argv) >= 3:
        endpoint = sys.argv[2].lower()

    print(f"Using Ollama model: {model} (endpoint: {endpoint}) (CTRL-C to exit)")
    try:
        while True:
            prompt = input("You: ")
            if not prompt.strip():
                continue
            if endpoint in ("completions", "completion", "legacy"):
                response = query_ollama(model, prompt)
            else:
                response = query_ollama_chat(model, prompt)
            print(f"Ollama: {response}\n")
    except KeyboardInterrupt:
        print("\nBye!")


if __name__ == "__main__":
    main()

#python ollama_client.py [model]
