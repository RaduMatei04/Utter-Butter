"""
commands.py: transformă textul recunoscut într-o comandă.

    "Next step, please."          -> {"action": "next",  "value": None}
    "Pornește timer 5 minute"     -> {"action": "timer", "value": 5}
    "ce mai faci azi?"            -> {"action": "unknown", "value": None}
"""

import difflib
import re
import unicodedata

# Dicționarul de comenzi: SINGURUL loc unde se adaugă expresii noi.
# Expresiile sunt scrise fără diacritice și cu litere mici.
COMMANDS = {
    "next":        ["next", "next step", "continue", "go on", "forward",
                    "urmatorul", "pasul urmator", "urmatorul pas", "inainte", "mai departe", "continua"],
    "previous":    ["back", "go back", "previous", "previous step",
                    "inapoi", "pasul anterior", "pasul precedent", "anterior"],
    "repeat":      ["repeat", "again", "say again", "one more time", "repeta", "din nou", "inca o data"],
    "ingredients": ["ingredients", "ingredient", "show ingredients", "what do i need",
                    "ingrediente", "ingredientele"],
    "close":       ["close", "hide", "close it", "inchide", "ascunde"],
    "timer":       ["timer", "start timer", "start a timer", "set timer", "set a timer",
                    "porneste timer", "porneste timerul", "seteaza timer", "cronometru", "timerul"],
    "stop_timer":  ["stop", "stop timer", "stop the timer", "stop alarm", "cancel timer",
                    "opreste", "opreste timer", "opreste timerul", "opreste alarma"],
    "read":        ["read", "read step", "read it", "read aloud", "citeste", "citeste pasul"],
    "help":        ["help", "what can i say", "commands", "ajutor", "ce pot spune", "comenzi"],
    "exit":        ["exit", "quit", "go home", "back home", "back to home", "finish cooking",
                    "iesire", "iesi", "acasa", "inchide reteta"],
}

NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "sixty": 60,
    "un": 1, "unu": 1, "o": 1, "doi": 2, "doua": 2, "trei": 3, "patru": 4, "cinci": 5,
    "sase": 6, "sapte": 7, "opt": 8, "noua": 9, "zece": 10, "cincisprezece": 15,
    "douazeci": 20, "treizeci": 30, "patruzeci": 40, "saizeci": 60,
}

MAX_WORDS = 8   # o frază mai lungă e conversație, nu o comandă (microfonul ascultă tot timpul)


def normalize(text):
    """'Pornește Timer-ul, 5 minute!' -> 'porneste timer ul 5 minute'"""
    text = unicodedata.normalize("NFD", text.lower())                     # „ș” -> „s” + semn
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")  # scoatem semnele
    return re.sub(r"[^a-z0-9]+", " ", text).strip()                        # fără punctuație


def find_action(text):
    """Căutăm expresiile din COMMANDS în text. Cea mai LUNGĂ găsită câștigă,
    ca „stop timer” să fie ales înaintea lui „timer”."""
    padded = f" {text} "
    found = [(len(phrase), action)
             for action, phrases in COMMANDS.items()
             for phrase in phrases
             if f" {phrase} " in padded]
    if found:
        return max(found)[1]

    # Rezervă: un cuvânt foarte asemănător cu o comandă (ex: Whisper a scris „ingridients”)
    single_words = {p: a for a, phrases in COMMANDS.items() for p in phrases if " " not in p}
    for word in text.split():
        if len(word) >= 4:
            match = difflib.get_close_matches(word, single_words, n=1, cutoff=0.8)
            if match:
                return single_words[match[0]]
    return None


def find_number(words):
    """Primul număr din text: cifre ('5') sau cuvinte ('five', 'douazeci si cinci')."""
    total = None
    for word in words:
        if word.isdigit():
            return int(word)
        if word in NUMBERS:
            total = (total or 0) + NUMBERS[word]   # „twenty five” = 20 + 5
        elif total is not None and word not in ("and", "si"):
            break
    return total


def interpret(transcript):
    text = normalize(transcript or "")
    words = text.split()
    if not words or len(words) > MAX_WORDS:
        return {"action": "unknown", "value": None}

    action = find_action(text) or "unknown"
    value = find_number(words) if action == "timer" else None
    return {"action": action, "value": value}


# Test rapid:  docker compose exec speech python commands.py
if __name__ == "__main__":
    for example in ["Next step, please.", "Pasul următor!", "Înapoi", "Start timer 5 minutes",
                    "Pornește timer cinci minute", "timer douăzeci și cinci de minute",
                    "Stop the timer", "Oprește timerul", "Ingridients", "Ce pot spune?",
                    "Citește", "Ieșire", "Thank you.",
                    "I was telling my friend that the next movie is great tonight"]:
        print(f"{example!r:65} -> {interpret(example)}")
