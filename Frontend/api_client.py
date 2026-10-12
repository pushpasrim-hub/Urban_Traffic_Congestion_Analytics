import os
from typing import Any

import requests


class APIError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class APIClient:
    def __init__(self, base_url: str | None = None, timeout: int = 10):
        self.base_url = (base_url or os.getenv("API_BASE_URL", "http://127.0.0.1:8000/api")).rstrip("/")
        self.timeout = timeout
        self.token: str | None = None

    def set_token(self, token: str | None) -> None:
        self.token = token

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = dict(kwargs.pop("headers", {}))
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            response = requests.request(
                method,
                f"{self.base_url}/{path.lstrip('/')}",
                headers=headers,
                timeout=self.timeout,
                **kwargs,
            )
        except requests.Timeout:
            raise APIError("The API request timed out. Try refreshing in a moment.") from None
        except requests.ConnectionError:
            raise APIError("FastAPI is unreachable. Start the backend and check API_BASE_URL.") from None
        except requests.RequestException:
            raise APIError("The request could not be completed.") from None

        if not response.ok:
            message = "The API rejected the request."
            try:
                detail = response.json().get("detail")
                if isinstance(detail, str):
                    message = detail
                elif detail:
                    message = "; ".join(
                        str(item.get("msg", item)) if isinstance(item, dict) else str(item)
                        for item in detail
                    )
            except (ValueError, AttributeError):
                pass
            raise APIError(message, response.status_code)
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            raise APIError("The API returned an unreadable response.", response.status_code) from None

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self.request("GET", path, params=params)

    def post(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        return self.request("POST", path, json=payload)

    def put(self, path: str, payload: dict[str, Any]) -> Any:
        return self.request("PUT", path, json=payload)

    def patch(self, path: str, payload: dict[str, Any]) -> Any:
        return self.request("PATCH", path, json=payload)

    def delete(self, path: str) -> Any:
        return self.request("DELETE", path)