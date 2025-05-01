from __future__ import annotations

import argparse
import base64
import binascii
import bisect
import importlib
import re
import string
from pathlib import Path
from typing import Callable, Dict, List, Sequence

# ----------------------------- dictionary --------------------------------- #

def load_dictionary(path: Path) -> List[str]:
    words = [w.strip().lower() for w in path.read_text(encoding="utf-8", errors="ignore").splitlines() if w.strip()]
    words.sort()
    return words


def in_dictionary(word: str, dictionary: List[str]) -> bool:
    idx = bisect.bisect_left(dictionary, word)
    return idx < len(dictionary) and dictionary[idx] == word

# ----------------------------- decoders ----------------------------------- #
Decoder = Callable[[bytes], bytes]


def _make_stdlib_decoder(std_name: str) -> Decoder:
    fn = getattr(base64, f"{std_name}decode")

    def _decoder(data: bytes) -> bytes:
        try:
            return fn(data, validate=True)  # type: ignore[arg-type]
        except TypeError:
            return fn(data)

    return _decoder

STD_BASES: Dict[str, Decoder] = {name: _make_stdlib_decoder(name) for name in ("b16", "b32", "b64")}
STD_BASES["b85"] = base64.b85decode

try:
    base58_mod = importlib.import_module("base58")
    STD_BASES["b58"] = lambda d: base58_mod.b58decode(d.decode())  # type: ignore[assignment]
except ModuleNotFoundError:
    pass

# ----------------------------- caesar ------------------------------------- #
ALPHA = string.ascii_lowercase
ALPHA_UP = ALPHA.upper()
LEN_ALPHA = 26

def caesar(text: str, shift: int) -> str:
    trans = str.maketrans(ALPHA + ALPHA_UP,
                          ALPHA[shift:] + ALPHA[:shift] + ALPHA_UP[shift:] + ALPHA_UP[:shift])
    return text.translate(trans)

# ----------------------------- helpers ------------------------------------ #
WORD_RE = re.compile(r"[A-Za-z]+")


def first_word(text: str) -> str | None:
    m = WORD_RE.search(text)
    return m.group(0).lower() if m else None


def evaluate_candidate(name: str, data: bytes, dictionary: List[str]) -> Dict[str, str | bool]:
    try:
        txt = data.decode("utf-8")
    except UnicodeDecodeError:
        txt = data.decode("latin-1", errors="replace")
    word = first_word(txt)
    match = in_dictionary(word, dictionary) if word else False
    return {
        "candidate": name,
        "word": word or "(none)",
        "match": match,
        "preview": repr(txt[:60]),
    }

# ------------------------- main routine ----------------------------------- #

def run(path: Path, dict_path: Path, debug: bool = False) -> None:
    dictionary = load_dictionary(dict_path)
    raw = path.read_bytes()
    results: List[Dict[str, str | bool]] = []

    # Original
    results.append(evaluate_candidate("original", raw, dictionary))

    # Bases
    for tag, decoder in STD_BASES.items():
        try:
            decoded = decoder(raw)
        except Exception:
            if debug:
                print(f"[DEBUG] {tag} failed")
            continue
        results.append(evaluate_candidate(tag, decoded, dictionary))

    # Caesar 1‑50
    raw_text = raw.decode("latin-1", errors="replace")
    for s in range(1, 51):
        shifted = caesar(raw_text, s).encode()
        results.append(evaluate_candidate(f"rot{s}", shifted, dictionary))

    # Print matches first, then the rest
    matches = [r for r in results if r["match"]]
    non_matches = [r for r in results if not r["match"]]

    if matches:
        print("\n*** Dictionary matches ***")
        for r in matches:
            print(f"{r['candidate']:<7}  first word='{r['word']}'  preview={r['preview']}")
    else:
        print("No direct dictionary match; showing all candidates (first 10)…")
    for r in (matches or non_matches)[:10]:
        if r in matches:
            continue  # already printed
        print(f"{r['candidate']:<7}  first word='{r['word']}'  preview={r['preview']}")

# ------------------------- CLI ------------------------------------------- #

def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Guess decoding/ROT by checking first‑word dictionary hits")
    parser.add_argument("file", type=Path, help="Input text file to test")
    parser.add_argument("--dict", type=Path, default=Path("words.txt"), help="Word list (one word per line)")
    parser.add_argument("--debug", action="store_true", help="Verbose decoder failures")
    args = parser.parse_args(argv)

    run(args.file, args.dict, debug=args.debug)

if __name__ == "__main__":
    main()
