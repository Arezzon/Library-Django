"""Small query-time name/title normalization; no model or stored reader data."""

import re
import unicodedata

from django.db.models import CharField, Func, Value
from django.db.models.functions import Lower, Replace

# Transliteration is deliberately deterministic, not a claim to translate names.
DIGRAPHS = {
    "щ": "shch",
    "ш": "sh",
    "ч": "ch",
    "ж": "zh",
    "х": "kh",
    "ц": "ts",
    "є": "ye",
    "ї": "yi",
    "ю": "yu",
    "я": "ya",
    "ё": "yo",
}
SINGLES = str.maketrans(
    {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "h",
        "ґ": "g",
        "д": "d",
        "е": "e",
        "з": "z",
        "и": "y",
        "і": "i",
        "й": "y",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "ь": " ",
        "ъ": " ",
        "э": "e",
        "ы": "y",
    }
)
ENDINGS = (
    "ові",
    "еві",
    "ого",
    "ому",
    "ами",
    "ями",
    "ою",
    "ею",
    "ів",
    "их",
    "ій",
    "ої",
    "а",
    "я",
    "у",
    "ю",
    "і",
    "и",
    "о",
)


def fold(value):
    value = unicodedata.normalize("NFKC", value).casefold()
    for source, target in DIGRAPHS.items():
        value = value.replace(source, target)
    value = value.translate(SINGLES).replace("ь", "").replace("ъ", "")
    value = value.replace("kh", "h").replace("y", "i").replace("w", "v")
    value = re.sub(r"[^a-z0-9]", "", value)
    return re.sub(r"([a-z])\1+", r"\1", value)


def tokens(query):
    """Conservative Ukrainian case stems; English words keep their endings."""
    result = []
    for word in re.findall(r"[^\W_]+(?:['’][^\W_]+)?", query.casefold()):
        if word.endswith(("'s", "’s")):
            word = word[:-2]
        if re.search("[а-яіїєґ]", word):
            for ending in ENDINGS:
                if word.endswith(ending) and len(word) - len(ending) >= 3:
                    word = word[: -len(ending)]
                    break
        value = fold(word)
        if value:
            result.append(value)
    return result


class RegexpReplace(Func):
    function = "REGEXP_REPLACE"
    output_field = CharField()


def folded_field(field):
    """Match in PostgreSQL without loading catalog rows into Python memory."""
    expression = Lower(field)
    for source, target in DIGRAPHS.items():
        expression = Replace(expression, Value(source), Value(target))
    # Translate the remaining one-character mappings in one database operation.
    expression = Func(
        expression,
        Value("".join(chr(c) for c in SINGLES)),
        Value("".join(SINGLES.values())),
        function="TRANSLATE",
        output_field=CharField(),
    )
    for source, target in (("kh", "h"), ("y", "i"), ("w", "v")):
        expression = Replace(expression, Value(source), Value(target))
    expression = RegexpReplace(expression, Value("[^a-z0-9]"), Value(""), Value("g"))
    return RegexpReplace(expression, Value(r"([a-z])\1+"), Value(r"\1"), Value("g"))
