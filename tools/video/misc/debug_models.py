import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

api_key = os.environ.get("GEMINI_API_KEY")
print(f"API Key present: {bool(api_key)}")

client = genai.Client(api_key=api_key)

print("\n--- Listing Models ---")
try:
    # New SDK might not have a direct list_models on client.models? 
    # Actually it does usually via list() or similar. 
    # Let's try to just generate content first as listing might be different.
    # But wait, I need to know the valid model names.
    # The HTTP API has detailed list.
    pass
except Exception as e:
    print(f"List models failed: {e}")

print("\n--- Testing Generation with gemini-1.5-pro ---")
try:
    response = client.models.generate_content(
        model="gemini-1.5-pro",
        contents="Hello, this is a test.",
    )
    print(f"Success! Response: {response.text}")
except Exception as e:
    print(f"gemini-1.5-pro failed: {e}")

print("\n--- Testing Generation with gemini-2.0-flash ---")
try:
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents="Hello, this is a test.",
    )
    print(f"Success! Response: {response.text}")
except Exception as e:
    print(f"gemini-2.0-flash failed: {e}")

print("\n--- Testing Generation with models/gemini-1.5-pro (prefix) ---")
try:
    response = client.models.generate_content(
        model="models/gemini-1.5-pro",
        contents="Hello, this is a test.",
    )
    print(f"Success! Response: {response.text}")
except Exception as e:
    print(f"models/gemini-1.5-pro failed: {e}")
