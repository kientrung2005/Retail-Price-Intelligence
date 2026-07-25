from urllib.parse import urlparse

def normalize_url(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    except Exception:
        return url
