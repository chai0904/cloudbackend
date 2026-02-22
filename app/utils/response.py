"""
Standard API response format and utility functions.
"""

from typing import Any, Optional


def success_response(data: Any = None, message: str = "Success") -> dict:
    return {"success": True, "data": data, "message": message}


def error_response(message: str = "Error", data: Any = None) -> dict:
    return {"success": False, "data": data, "message": message}
