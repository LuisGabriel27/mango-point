"""Shared, offline-safe validation for account and contact inputs."""
import re


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > 254 or email.count("@") != 1:
        raise ValueError("Enter a valid email address.")
    local, domain = email.split("@")
    labels = domain.split(".")
    if (not local or len(local) > 64 or local.startswith(".") or local.endswith(".")
            or ".." in local or not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+", local)
            or len(labels) < 2 or labels[-1].isdigit()
            or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels)):
        raise ValueError("Enter a valid email address.")
    return email


def normalize_person_name(value: str) -> str:
    if any(ord(char) < 32 or ord(char) == 127 or char in "<>" for char in value):
        raise ValueError("Name cannot contain control characters or angle brackets.")
    name = " ".join(value.split())
    if not name or len(name) > 200 or not any(char.isalpha() for char in name):
        raise ValueError("Enter a name with at least one letter, up to 200 characters.")
    return name
