import requests

_session = requests.Session()


def request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: dict | None = None,
    timeout: float = 30,
    allow_redirects: bool = True,
) -> requests.Response:
    return _session.request(
        method,
        url,
        headers=headers,
        json=json_body,
        timeout=timeout,
        allow_redirects=allow_redirects,
    )
