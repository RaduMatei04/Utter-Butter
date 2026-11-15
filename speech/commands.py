"""
commands.py: transformă textul recunoscut (transcrierea) într-o comandă.

Exemple:
    "Next step, please."        -> {"action": "next",  "value": None}
    "Pornește timer 5 minute"   -> {"action": "timer", "value": 5}
    "start timer thirty seconds" -> {"action": "timer", "value": 0.5}
    "ce mai faci azi?"          -> {"action": "unknown", "value": None}

Pași:
  1. normalizare: litere mici, fără diacritice, fără punctuație
  2. căutare de expresii-cheie (cea mai LUNGĂ expresie găsită câștigă,
     ca „stop timer” să fie ales înaintea lui „timer”)
  3. rezervă: potrivire aproximativă (difflib) pe cuvinte, pentru greșeli mici
  4. pentru „timer”: extragem numărul (cifre sau cuvinte, EN și RO)
"""

import difflib
import re
import unicodedata

# ---------------------------------------------------------------------
# Dicționarul de comenzi: SINGURUL loc unde se adaugă expresii noi.
# Expresiile sunt scrise deja normalizate (fără diacritice, litere mici).
# ---------------------------------------------------------------------
COMMANDS = {
    "next": [
        "next", "next step", "continue", "go on", "forward",
        "urmatorul", "pasul urmator", "urmatorul pas", "inainte", "mai departe", "continua",
    ],
    "previous": [
        "back", "go back", "previous", "previous step",
        "inapoi", "pasul anterior", "pasul precedent", "anterior",
    ],
    "repeat": [
        "repeat", "again", "say again", "one more time",
        "repeta", "din nou", "inca o data",
    ],
    "ingredients": [
        "ingredients", "ingredient", "show ingredients", "what do i need",
        "ingrediente", "ingredientele",
    ],
    "close": [
        "close", "hide", "close it",
        "inchide", "ascunde",
    ],
    "timer": [
        "timer", "start timer", "start a timer", "set timer", "set a timer",
        "porneste timer", "porneste timerul", "seteaza timer", "cronometru", "timerul",
    ],
    "stop_timer": [
        "stop", "stop timer", "stop the timer", "stop alarm", "cancel timer",
        "opreste", "opreste timer", "opreste timerul", "opreste alarma",
    ],
    "read": [
        "read", "read step", "read it", "read aloud",
        "citeste", "citeste pasul",
    ],
    "help": [
        "help", "what can i say", "commands",
        "ajutor", "ce pot spune", "comenzi",
    ],
    "exit": [
        "exit", "quit", "go home", "back home", "back to home", "finish cooking",
        "iesire", "iesi", "acasa", "inchide reteta",
    ],
}

# O frază lungă e aproape sigur conversație normală, nu o comandă.
# (Microfonul ascultă continuu, așa că filtrăm frazele cu prea multe cuvinte.)
MAX_WORDS = 8

# Toate perechile (expresie, acțiune), sortate de la cea mai lungă la cea mai scurtă
PHRASES = sorted(
    ((phrase, action) for action, phrases in COMMANDS.items() for phrase in phrases),
    key=lambda pair: len(pair[0]),
    reverse=True,
)

# Pentru potrivirea aproximativă folosim doar expresiile dintr-un singur cuvânt
SINGLE_WORDS = {phrase: action for phrase, action in PHRASES if " " not in phrase}

# ---------------------------------------------------------------------
# Numere scrise în cuvinte (engleză + română, normalizate)
# ---------------------------------------------------------------------
NUMBER_WORDS = {
    # engleză
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    # română
    "un": 1, "unu": 1, "una": 1, "o": 1, "doi": 2, "doua": 2, "trei": 3, "patru": 4,
    "cinci": 5, "sase": 6, "sapte": 7, "opt": 8, "noua": 9, "zece": 10,
    "unsprezece": 11, "doisprezece": 12, "douasprezece": 12, "treisprezece": 13,
    "paisprezece": 14, "cincisprezece": 15, "saisprezece": 16, "saptesprezece": 17,
    "optsprezece": 18, "nouasprezece": 19, "douazeci": 20, "treizeci": 30,
    "patruzeci": 40, "cincizeci": 50, "saizeci": 60,
}


def normalize(text):
    """'Pornește Timer-ul, 5 minute!' -> 'porneste timer ul 5 minute'"""
    text = text.lower()
    # NFD desparte litera de semnul diacritic (ș -> s + virgulă dedesubt),
    # apoi eliminăm semnele (categoria „Mn” = mark, nonspacing)
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    # orice nu e literă sau cifră devine spațiu
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return text.strip()


def extract_number(words):
    """Caută primul număr din listă: cifre ('5'), cuvinte ('five', 'cinci')
    sau numere compuse ('twenty five', 'douazeci si cinci'). Întoarce None dacă nu găsește."""
    for i, word in enumerate(words):
        if word.isdigit():
            return int(word)
        if word in NUMBER_WORDS:
            number = NUMBER_WORDS[word]
            # număr compus: zeci + (opțional „and”/„si”) + unități
            if number >= 20:
                j = i + 1
                if j < len(words) and words[j] in ("and", "si"):
                    j += 1
                if j < len(words) and NUMBER_WORDS.get(words[j], 99) < 10:
                    number += NUMBER_WORDS[words[j]]
            return number
    return None


def extract_timer_minutes(words):
    """Durata timer-ului, în minute. „30 seconds” / „30 secunde” -> 0.5"""
    number = extract_number(words)
    if number is None:
        return None
    if any(w.startswith("second") or w.startswith("secund") for w in words):
        return round(number / 60, 2)
    return number


def find_action(text, words):
    """Întoarce acțiunea găsită în text sau None."""
    padded = f" {text} "
    # 1) potrivire exactă: cea mai lungă expresie conținută în text
    for phrase, action in PHRASES:
        if f" {phrase} " in padded:
            return action

    # 2) potrivire aproximativă: un cuvânt foarte asemănător cu o comandă
    #    (ex: Whisper a scris „nex” sau „ingridients”)
    for word in words:
        if len(word) < 4:
            continue  # cuvintele scurte se confundă prea ușor
        match = difflib.get_close_matches(word, SINGLE_WORDS.keys(), n=1, cutoff=0.8)
        if match:
            return SINGLE_WORDS[match[0]]
    return None


def interpret(transcript):
    """Funcția principală: transcriere -> {"action": ..., "value": ...}"""
    text = normalize(transcript or "")
    words = text.split()

    if not words or len(words) > MAX_WORDS:
        return {"action": "unknown", "value": None}

    action = find_action(text, words)
    if action is None:
        return {"action": "unknown", "value": None}

    value = extract_timer_minutes(words) if action == "timer" else None
    return {"action": action, "value": value}


# Test rapid: python commands.py
if __name__ == "__main__":
    examples = [
        "Next step, please.", "Pasul următor!", "Go back", "Înapoi",
        "Start timer 5 minutes", "Pornește timer cinci minute",
        "set a timer for twenty five minutes", "timer douăzeci și cinci de minute",
        "start timer thirty seconds", "Stop the timer", "Oprește timerul",
        "Ingredients", "Ingridients", "What can I say?", "Ce pot spune?",
        "Read", "Citește", "Repeat", "Exit", "Ieșire", "close",
        "Thank you.", "I was telling my friend that the next movie is great tonight",
    ]
    for example in examples:
        print(f"{example!r:60} -> {interpret(example)}")
