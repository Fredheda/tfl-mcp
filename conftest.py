import os

# `create_agent("openai:...")` builds the OpenAI client at call time, which
# requires a key to be present (it is never used — these tests make no live
# calls). Provide a dummy one if the environment doesn't already have a real key.
os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy-key-not-used")
