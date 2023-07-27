"""Helper/utility functions"""
import re


def csv_bool_to_bool(csv_bool_str):
    """Converts an Excel/CSV-style Boolean string (TRUE/FALSE) into a Python bool"""
    if csv_bool_str.strip().lower() == "true":
        return True
    if csv_bool_str.strip().lower() == "false":
        return False
    return None


def is_nully_str(s):
    """
    Returns True if s is None, an empty or whitespace-filled string, or some variation of "NULL"
    """
    if s is None:
        return True
    s_strip = s.lower().strip()
    return s_strip in ["", "null"]


def is_valid_url(url):
    """Returns true if input is a valid HTTP(S) URL"""
    regex = re.compile(
        r"^https?://"  # http:// or https://
        r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"  # domain...
        r"localhost|"  # localhost...
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ...or ip
        r"(?::\d+)?"  # optional port
        r"(?:/?|[/?]\S+)$",
        re.IGNORECASE,
    )
    return url is not None and regex.search(url)
