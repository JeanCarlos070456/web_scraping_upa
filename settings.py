import os

def get_verify_ssl() -> bool:
    """
    Lê VERIFY_SSL sempre em runtime.
    Default: True (seguro). Desligue com VERIFY_SSL=false.
    """
    return os.getenv("VERIFY_SSL", "true").strip().lower() in ("1", "true", "yes", "y")
