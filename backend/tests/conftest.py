import os
import tempfile

# Must run before the app is imported: use a throwaway database and the offline keyword rules.
os.environ["RFP_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ.pop("OPENAI_API_KEY", None)
