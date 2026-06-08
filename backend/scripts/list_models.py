import json
import requests
from app.utils.config import settings

key = settings.gemini_api_key
if not key:
    print("NO_KEY")
    raise SystemExit(1)

resp = requests.get("https://generativelanguage.googleapis.com/v1beta/models", headers={"X-Goog-Api-Key": key}, timeout=30)
print(resp.status_code)
try:
    j = resp.json()
except Exception:
    print(resp.text)
    raise

# Print brief list of models and supported methods
models = j.get('models') or j.get('model') or []
if not isinstance(models, list):
    models = [models]
for m in models:
    name = m.get('name') or m.get('model') or '<unknown>'
    methods = m.get('supported_methods') or m.get('capabilities') or []
    print(name)
    if isinstance(methods, list):
        print('  methods:', ', '.join(str(x) for x in methods))
    else:
        print('  meta:', json.dumps(methods))

print('\nFull response truncated:')
print(json.dumps(j, indent=2)[:4000])
