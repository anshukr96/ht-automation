import os


def use_free_providers() -> bool:
    return os.getenv("USE_FREE_PROVIDERS", "0").lower() in {"1", "true", "yes"}
