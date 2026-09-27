"""Windows TLS compatibility entry point for ingest_official_congbao_labor."""

from __future__ import annotations

from urllib.parse import urlparse

import requests
import urllib3

import ingest_official_congbao_labor as ingest


_original_get = requests.Session.get


def _get_with_official_cdn_fallback(self, url, **kwargs):
    try:
        return _original_get(self, url, **kwargs)
    except requests.exceptions.SSLError:
        if urlparse(str(url)).hostname != "g7.cdnchinhphu.vn":
            raise
        fallback_kwargs = dict(kwargs)
        fallback_kwargs["verify"] = False
        return _original_get(self, url, **fallback_kwargs)


requests.Session.get = _get_with_official_cdn_fallback
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


if __name__ == "__main__":
    raise SystemExit(ingest.main())
