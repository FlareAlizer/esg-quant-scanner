import os

# Settings are read at import. Pin them so a local .env or the shell cannot
# change what the tests see, and so nothing can reach a real LLM.
os.environ["LLM_API_KEY"] = ""
os.environ["RISK_FREE_RATE"] = "0.04"
os.environ["RANDOM_SEED"] = "42"
