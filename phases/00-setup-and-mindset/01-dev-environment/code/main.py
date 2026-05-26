"""
Lesson 01: Dev Environment
Verifies that the Python environment and Anthropic SDK are correctly installed.
Run with: uv run python main.py
"""

import sys
import os

# Step 1: Verify Python version
print(f"Python version: {sys.version}")
major, minor = sys.version_info.major, sys.version_info.minor
if major < 3 or (major == 3 and minor < 11):
    print("WARNING: Python 3.11+ is recommended for this course.")
else:
    print(f"OK: Python {major}.{minor} meets the 3.11+ requirement.")

# Step 2: Verify Anthropic SDK import
try:
    import anthropic
    print(f"OK: anthropic SDK version {anthropic.__version__} imported successfully.")
except ImportError:
    print("ERROR: 'anthropic' not found. Run: uv add anthropic")
    sys.exit(1)

# Step 3: Verify API key is present
api_key = os.environ.get("ANTHROPIC_API_KEY")
if not api_key:
    print("WARNING: ANTHROPIC_API_KEY not set. Set it before making API calls.")
    print("  export ANTHROPIC_API_KEY=sk-ant-...")
    print("Skipping API call verification.")
    sys.exit(0)

print("OK: ANTHROPIC_API_KEY found in environment.")

# Step 4: Make a minimal API call to confirm the key works
print("\nMaking a minimal API call to verify key and connectivity...")

client = anthropic.Anthropic(api_key=api_key)

message = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=32,
    messages=[
        {"role": "user", "content": "Reply with exactly: ENVIRONMENT OK"}
    ]
)

response_text = message.content[0].text
print(f"Model response: {response_text}")
print(f"Input tokens: {message.usage.input_tokens}")
print(f"Output tokens: {message.usage.output_tokens}")

if "ENVIRONMENT" in response_text.upper():
    print("\nAll checks passed. Your environment is ready.")
else:
    print("\nAPI call succeeded but response was unexpected. Environment is likely fine.")
