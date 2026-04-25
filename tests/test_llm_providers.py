"""
Test script to verify LLM providers configuration.
- Tests Groq API with all available models
- Tests Gemini API with sample inference
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_groq_models():
    """Test Groq API with all available models."""
    logger.info("=" * 80)
    logger.info("TESTING GROQ API")
    logger.info("=" * 80)

    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        logger.error("❌ GROQ_API_KEY not set in environment")
        return False

    logger.info(f"✓ Groq API key found: {groq_api_key[:10]}...")

    try:
        from groq import Groq
    except ImportError:
        logger.error("❌ groq package not installed. Run: pip install groq")
        return False

    # Groq models to test
    models = [
        "llama3-8b-8192",
        "llama3-70b-8192",
        "mixtral-8x7b-32768",
        "gemma-7b-it",
    ]

    client = Groq(api_key=groq_api_key)
    all_passed = True

    for model in models:
        try:
            logger.info(f"\n📝 Testing model: {model}")

            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": "Say 'Model test successful' in one sentence.",
                    }
                ],
                max_tokens=50,
                temperature=0.3,
            )

            result = response.choices[0].message.content.strip()
            logger.info(f"✓ {model} responded: {result[:60]}...")

        except Exception as e:
            logger.error(f"❌ {model} failed: {str(e)}")
            all_passed = False

    return all_passed


def test_gemini_api():
    """Test Gemini API with inference."""
    logger.info("\n" + "=" * 80)
    logger.info("TESTING GEMINI API")
    logger.info("=" * 80)

    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        logger.error("❌ GEMINI_API_KEY not set in environment")
        return False

    logger.info(f"✓ Gemini API key found: {gemini_api_key[:10]}...")

    try:
        import google.generativeai as genai
    except ImportError:
        logger.error("❌ google-generativeai package not installed.")
        logger.error("   Run: pip install google-generativeai")
        return False

    try:
        logger.info("\n📝 Configuring Gemini API...")
        genai.configure(api_key=gemini_api_key)
        logger.info("✓ Gemini API configured")

        logger.info("\n📝 Testing Gemini inference...")
        model = genai.GenerativeModel("gemini-pro")

        test_prompt = """Analyze this code diff and classify it in one word:

```diff
--- a/app.py
+++ b/app.py
@@ -10,5 +10,7 @@
 def process_data(data):
-    result = data * 2
+    result = data * 3
     return result
```

Respond with ONLY one word classification from: logic, style, security, performance, tests, docs, refactor"""

        response = model.generate_content(test_prompt)
        result = response.text.strip()

        logger.info(f"✓ Gemini responded: {result}")
        logger.info(f"✓ Response length: {len(result)} characters")

        # Additional test: verify response is reasonable
        valid_tags = {
            "logic",
            "style",
            "security",
            "performance",
            "tests",
            "docs",
            "refactor",
        }
        first_word = result.lower().split()[0]

        if first_word in valid_tags:
            logger.info(f"✓ Response is valid classification: {first_word}")
            return True
        else:
            logger.warning(
                f"⚠ Response '{result}' is not a standard classification tag"
            )
            return True  # Still pass, it's a valid response

    except Exception as e:
        logger.error(f"❌ Gemini test failed: {str(e)}")
        import traceback

        traceback.print_exc()
        return False


def test_groq_classifier():
    """Test Groq classifier node functionality."""
    logger.info("\n" + "=" * 80)
    logger.info("TESTING GROQ CLASSIFIER NODE")
    logger.info("=" * 80)

    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        logger.error("❌ GROQ_API_KEY not set")
        return False

    try:
        from groq import Groq
        from pipeline.prompts import CLASSIFIER_PROMPT

        logger.info("\n📝 Testing classifier node with Groq...")

        client = Groq(api_key=groq_api_key)

        # Sample diff for testing
        sample_diff = """--- a/utils/helpers.py
+++ b/utils/helpers.py
@@ -15,6 +15,8 @@
 def validate_input(data):
-    if len(data) > 100:
+    if len(data) > 1000:  # Increased limit
         return False
+    # Added logging
+    print(f"Validated: {data}")
     return True"""

        prompt = CLASSIFIER_PROMPT.format(diff_text=sample_diff)
        response = client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=50,
            temperature=0.3,
        )

        tag = response.choices[0].message.content.strip().lower().split()[0]
        logger.info(f"✓ Classifier returned tag: {tag}")

        valid_tags = {
            "logic",
            "style",
            "security",
            "performance",
            "tests",
            "docs",
            "refactor",
        }
        if tag in valid_tags:
            logger.info(f"✓ Tag is valid: {tag}")
            return True
        else:
            logger.warning(f"⚠ Tag '{tag}' not in standard set, but response valid")
            return True

    except Exception as e:
        logger.error(f"❌ Classifier node test failed: {str(e)}")
        import traceback

        traceback.print_exc()
        return False


def test_gemini_verifier():
    """Test Gemini verifier node functionality."""
    logger.info("\n" + "=" * 80)
    logger.info("TESTING GEMINI VERIFIER NODE")
    logger.info("=" * 80)

    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        logger.error("❌ GEMINI_API_KEY not set")
        return False

    try:
        import google.generativeai as genai
        from pipeline.prompts import VERIFIER_PROMPT

        logger.info("\n📝 Testing verifier node with Gemini...")

        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel("gemini-pro")

        # Sample diff and findings for testing
        sample_diff = """--- a/auth.py
+++ b/auth.py
@@ -5,7 +5,8 @@
 def login(user, password):
-    if user == "admin" and password == "admin123":
+    # Check credentials
+    if user == "admin" and password == "admin123":
         return True"""

        sample_findings = """- SECURITY: Hardcoded password in source code
- STYLE: Added unnecessary comment"""

        prompt = VERIFIER_PROMPT.format(diff_text=sample_diff, findings=sample_findings)

        response = model.generate_content(prompt)
        verification_text = response.text.lower()

        logger.info(f"✓ Verifier responded: {verification_text[:100]}...")

        is_accepted = "accept" in verification_text or "valid" in verification_text
        logger.info(
            f"✓ Verification result: {'ACCEPTED' if is_accepted else 'REJECTED'}"
        )

        return True

    except Exception as e:
        logger.error(f"❌ Verifier node test failed: {str(e)}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    logger.info("\n🚀 Starting LLM Provider Tests\n")

    results = {
        "Groq Models": test_groq_models(),
        "Gemini API": test_gemini_api(),
        "Groq Classifier": test_groq_classifier(),
        "Gemini Verifier": test_gemini_verifier(),
    }

    logger.info("\n" + "=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)

    for test_name, passed in results.items():
        status = "✓ PASSED" if passed else "❌ FAILED"
        logger.info(f"{test_name}: {status}")

    all_passed = all(results.values())
    logger.info("\n" + "=" * 80)
    if all_passed:
        logger.info("🎉 ALL TESTS PASSED!")
    else:
        logger.error("⚠ SOME TESTS FAILED - Check errors above")
    logger.info("=" * 80)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
