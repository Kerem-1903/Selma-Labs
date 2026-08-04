import hashlib
import json
import urllib.parse
from typing import Any

class CacheKeyFactory:
    """
    Generates deterministic, collision-resistant cache keys.
    Format: {provider}:{url_encoded_query}:{sha256_hash_of_kwargs}
    """
    @staticmethod
    def generate(provider: str, query: str, **kwargs: Any) -> str:
        safe_provider = provider.lower().strip()
        safe_query = urllib.parse.quote(query.lower().strip())
        
        # Type-safe payload to prevent collisions (e.g. 1 vs "1")
        payload = {}
        for k, v in sorted(kwargs.items()):
            if v is not None:
                payload[k] = {
                    "type": type(v).__name__,
                    "value": str(v).strip()
                }
                
        serialized = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        hashed_params = hashlib.sha256(serialized.encode('utf-8')).hexdigest()
        
        return f"{safe_provider}:{safe_query}:{hashed_params}"
