import json
from dataclasses import asdict, is_dataclass

def stable_book_key(path: str) -> str:
    import hashlib, os
    return hashlib.sha256(os.path.abspath(path).encode()).hexdigest()
def json_dumps(value):
    def default(o): return asdict(o) if is_dataclass(o) else str(o)
    return json.dumps(value, default=default, ensure_ascii=False, sort_keys=True)
def stringify(value):
    if isinstance(value, (list, dict)): return json_dumps(value)
    return None if value is None else str(value)
