import os
import tempfile

# Must run before the app is imported: use a throwaway database and the offline keyword rules.
os.environ["RFP_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
for var in ["LLM_PROVIDER", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"]:
    os.environ.pop(var, None)
