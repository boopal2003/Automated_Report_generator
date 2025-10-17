# tests/test_api_key.py
import sys, os
BASE_DIR = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(BASE_DIR, "packages"))
sys.path.insert(0, BASE_DIR)


from openai import OpenAI
from config import OPENAI_API_KEY

import traceback

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

def test_openai_key():
    if not OPENAI_API_KEY:
        print("❌ OPENAI_API_KEY not set in environment.")
        return

    try:
        # Try modern import first (OpenAI SDK >= 1.x)
        try:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY)
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "Hello, are you working?"}],
                max_tokens=20
            )
            # Newer client: choices[0].message.content
            content = None
            if getattr(resp, "choices", None):
                ch0 = resp.choices[0]
                # Some SDKs put message under .message.content
                content = getattr(ch0, "message", None)
                if content:
                    content = content.content
                else:
                    # fallback
                    content = getattr(ch0, "text", None) or str(ch0)
            print("✅ OpenAI API (modern client) responded:", content)
            return

        except Exception as e_modern:
            # Fallback to legacy openai package interface
            import openai
            openai.api_key = OPENAI_API_KEY
            try:
                resp = openai.ChatCompletion.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": "Hello, are you working?"}],
                    max_tokens=20
                )
                # Legacy: resp.choices[0].message.content or resp.choices[0].text
                content = None
                if resp and "choices" in resp and len(resp["choices"]) > 0:
                    ch0 = resp["choices"][0]
                    if isinstance(ch0, dict):
                        content = (ch0.get("message") or {}).get("content") or ch0.get("text")
                    else:
                        content = getattr(ch0, "text", None) or str(ch0)
                print("✅ OpenAI API (legacy client) responded:", content)
                return
            except Exception as e_legacy:
                print("❌ OpenAI API call failed (legacy attempt).")
                traceback.print_exc()
                return

    except Exception as e:
        print("❌ OpenAI API key test failed (unexpected).")
        traceback.print_exc()

if __name__ == "__main__":
    test_openai_key()
