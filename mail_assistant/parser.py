"""Parse the structured analysis text produced by Claude into a dict."""
from __future__ import annotations

import re

FIELDS = [
    ("KATEGORIE", "kategorie"),
    ("PRIORITÄT", "prioritaet"),
    ("SICHERHEITSRISIKO", "sicherheitsrisiko"),
    ("PHISHING-VERDACHT", "phishing_verdacht"),
    ("ANTWORT ERFORDERLICH", "antwort_erforderlich"),
    ("ZUSAMMENFASSUNG", "zusammenfassung"),
    ("BEGRÜNDUNG", "begruendung"),
    ("ANTWORTENTWURF", "antwortentwurf"),
    ("EMPFOHLENE AKTION", "empfohlene_aktion"),
    ("FREIGABE ERFORDERLICH", "freigabe_erforderlich"),
]


def parse_analysis(text: str) -> dict:
    """Extract each labeled section from the model's structured response.

    Falls back to empty string for any section that couldn't be found so
    downstream code never has to guess at missing keys.
    """
    result = {key: "" for _, key in FIELDS}
    labels = [label for label, _ in FIELDS]

    for i, (label, key) in enumerate(FIELDS):
        next_labels = "|".join(re.escape(l) for l in labels[i + 1 :])
        if next_labels:
            pattern = rf"{re.escape(label)}:\s*(.*?)(?=\n(?:{next_labels}):|\Z)"
        else:
            pattern = rf"{re.escape(label)}:\s*(.*)\Z"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            result[key] = match.group(1).strip()

    result["is_security_risk"] = result["sicherheitsrisiko"].strip().upper().startswith("JA")
    result["is_phishing"] = result["phishing_verdacht"].strip().upper().startswith("JA")
    result["needs_approval"] = result["freigabe_erforderlich"].strip().upper().startswith("JA")

    return result
