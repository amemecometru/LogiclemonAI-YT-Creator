PLAN_ORDER = {"free": 0, "pro": 1}

MODELS = [
    {"id": "google/gemma-4-26b-a4b-it",          "label": "Gemma 4 26B A4B","min_plan": "free", "default_for": ["free"]},
    {"id": "google/gemini-2.0-flash-001",        "label": "Gemini 2.0 Flash","min_plan": "free"},
    {"id": "meta-llama/llama-3.3-70b-instruct",  "label": "Llama 3.3 70B",   "min_plan": "free"},
    {"id": "deepseek/deepseek-chat",             "label": "DeepSeek V3",     "min_plan": "free"},
    {"id": "openai/gpt-4o-mini",                 "label": "GPT-4o mini",     "min_plan": "pro", "default_for": ["pro"]},
    {"id": "openai/gpt-4o",                      "label": "GPT-4o",          "min_plan": "pro"},
    {"id": "anthropic/claude-3.7-sonnet",        "label": "Claude 3.7 Sonnet","min_plan": "pro"},
]

DEFAULT_MODEL = "google/gemma-4-26b-a4b-it"

def model_ids() -> set[str]:
    return {m["id"] for m in MODELS}

def default_for_plan(plan: str) -> str:
    for m in MODELS:
        if plan in m.get("default_for", []):
            return m["id"]
    return DEFAULT_MODEL

def is_allowed(model_id: str, plan: str, byok: bool) -> bool:
    m = next((x for x in MODELS if x["id"] == model_id), None)
    if m is None:
        return False
    if byok:
        return True
    return PLAN_ORDER.get(plan, 0) >= PLAN_ORDER.get(m["min_plan"], 99)
