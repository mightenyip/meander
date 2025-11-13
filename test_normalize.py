#!/usr/bin/env python3
import re

def normalize_character_name(name: str) -> str:
    """Normalize character name"""
    # Handle both straight and curly apostrophes in CONT'D
    name = re.sub(r"\s*\(CONT[''']D\)", '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s*\(V\.O\.\)', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s*\(O\.S\.\)', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s*#\d+', '', name)
    return name.strip()

# Test cases
test_names = [
    "PAISLEY (CONT'D)",
    "PAISLEY (CONT'D)",
    "KATHERINE (CONT'D)",
    "PRESIDENT JOHN F. KENNEDY (V.O.)",
    "UPPERCLASSMAN (O.S.)",
    "JOHN #2",
]

for name in test_names:
    normalized = normalize_character_name(name)
    print(f"{name:40} -> {normalized}")


