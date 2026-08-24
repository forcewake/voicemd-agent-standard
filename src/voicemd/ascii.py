from __future__ import annotations

import re
import unicodedata

PUNCTUATION = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u2026": "...",
        "\u00a0": " ",
        "\u2022": "-",
        "\u00b0": " degrees ",
        "\u2192": " -> ",
        "\u2190": " <- ",
        "\u2264": " <= ",
        "\u2265": " >= ",
        "\u2260": " != ",
    }
)

CYRILLIC = {
    "А": "A", "а": "a", "Б": "B", "б": "b", "В": "V", "в": "v",
    "Г": "G", "г": "g", "Д": "D", "д": "d", "Е": "E", "е": "e",
    "Ё": "Yo", "ё": "yo", "Ж": "Zh", "ж": "zh", "З": "Z", "з": "z",
    "И": "I", "и": "i", "Й": "Y", "й": "y", "К": "K", "к": "k",
    "Л": "L", "л": "l", "М": "M", "м": "m", "Н": "N", "н": "n",
    "О": "O", "о": "o", "П": "P", "п": "p", "Р": "R", "р": "r",
    "С": "S", "с": "s", "Т": "T", "т": "t", "У": "U", "у": "u",
    "Ф": "F", "ф": "f", "Х": "Kh", "х": "kh", "Ц": "Ts", "ц": "ts",
    "Ч": "Ch", "ч": "ch", "Ш": "Sh", "ш": "sh", "Щ": "Shch", "щ": "shch",
    "Ъ": "", "ъ": "", "Ы": "Y", "ы": "y", "Ь": "", "ь": "",
    "Э": "E", "э": "e", "Ю": "Yu", "ю": "yu", "Я": "Ya", "я": "ya",
    "І": "I", "і": "i", "Ї": "Yi", "ї": "yi", "Є": "Ye", "є": "ye",
    "Ґ": "G", "ґ": "g", "Ў": "U", "ў": "u",
}


def to_ascii(text: str) -> str:
    """Convert text into conservative, TTS-friendly ASCII."""
    translated = text.translate(PUNCTUATION)
    translated = "".join(CYRILLIC.get(char, char) for char in translated)
    normalized = unicodedata.normalize("NFKD", translated)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_text = re.sub(r"[ \t]+", " ", ascii_text)
    ascii_text = re.sub(r" *\n *", "\n", ascii_text)
    ascii_text = re.sub(r"\n{3,}", "\n\n", ascii_text)
    return ascii_text.strip(" \t\n\r")
