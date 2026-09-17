#!/usr/bin/env python3
"""Cross-check ktoy's Levenshtein-ratio did-you-mean against pytoy's difflib.

pytoy assembler._did_you_mean uses difflib.get_close_matches(cutoff=0.6),
which ranks by SequenceMatcher.ratio() = 2*M/T (M = matching chars, T = total
length of both strings). ktoy Assembler.didYouMean uses a Levenshtein ratio
1 - dist/max(len). Different algorithms -> can disagree on the suggestion.

Run: python3 tests/review_didyoumean_check.py
Prints every input where the two suggestions differ.
"""
import difflib

OPCODES = ['stop', 'right', 'left', 'not', 'and', 'or', 'xor', 'load',
           'store', 'add', 'sub', 'goto', 'ifzero', 'nop']


def python_suggest(word):
    m = difflib.get_close_matches(word.lower(), OPCODES, n=1, cutoff=0.6)
    return m[0] if m else None


def levenshtein(a, b):
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[len(b)]


def kotlin_suggest(word):
    """Mirror of ktoy didYouMean: first opcode reaching bestRatio wins ties
    (>= keeps updating, so among equal ratios the LAST in iteration order wins).
    OPCODES iteration order is the map's insertion order (same list here)."""
    w = word.lower()
    best = None
    best_ratio = 0.6
    for op in OPCODES:
        dist = levenshtein(w, op)
        ratio = 1.0 - dist / max(len(w), len(op))
        if ratio >= best_ratio:
            best_ratio = ratio
            best = op
    return best


TESTS = ['addd', 'looad', 'nope', 'xoor', 'goto', 'ad', 'lod', 'noo', 'stpo',
         'orr', 'adn', 'sob', 'iffzero', 'stre', 'goo', 'sto', 'ldoa', 'laod',
         'nap', 'no', 'an', 'o', 'x', 'gato', 'ifzer', 'stor', 'xo', 'andd',
         'ors', 'nott', 'leftt', 'rght', 'rigt', 'lores', 'strore', 'gotoo']

if __name__ == '__main__':
    diffs = 0
    print(f"{'word':<10} {'python(difflib)':<18} {'kotlin(leven)':<15} DIFF")
    for t in TESTS:
        p = python_suggest(t)
        k = kotlin_suggest(t)
        flag = '  <<< DIFF' if p != k else ''
        if p != k:
            diffs += 1
        print(f"{t:<10} {str(p):<18} {str(k):<15}{flag}")
    print(f"\n{diffs} differing suggestions out of {len(TESTS)}")
