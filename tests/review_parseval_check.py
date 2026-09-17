#!/usr/bin/env python3
"""Cross-check ktoy parseVal against pytoy parse_val (int(s, 0)).

pytoy: 8-char 0/1 string -> base 2; else int(s, 0) (accepts 0x/0b/decimal,
0o octal, underscores, +/- sign, but REJECTS multi-digit leading zeros).
ktoy: 8-char 0/1 -> base 2; else lowercases and handles 0x/-0x/0b/-0b
prefixes, otherwise toInt(10). Divergences below change data-byte / operand
values or turn a valid token into an error (value 0).

Run: python3 tests/review_parseval_check.py
"""


def python_parse(s):
    s = s.strip()
    if len(s) == 8 and all(c in '01' for c in s):
        return int(s, 2)
    return int(s, 0)


def kotlin_parse(raw):
    s = raw.strip()
    if len(s) == 8 and all(c in '01' for c in s):
        return int(s, 2)
    lower = s.lower()
    # Kotlin toInt(16/2) does NOT accept underscores or a leading '+'.
    def to_int(txt, base):
        if '_' in txt or txt.startswith('+'):
            raise ValueError("kotlin toInt rejects _ and +")
        return int(txt, base)
    if lower.startswith('0x'):
        return to_int(lower[2:], 16)
    if lower.startswith('-0x'):
        return -to_int(lower[3:], 16)
    if lower.startswith('0b'):
        return to_int(lower[2:], 2)
    if lower.startswith('-0b'):
        return -to_int(lower[3:], 2)
    return to_int(s, 10)


TESTS = ['0', '5', '255', '0x1F', '0xFF', '0b101', '0X1F', '010', '+5', '-5',
         '-0x10', '-0b10', '00', '007', '0b11111111', '11111111', '12345678',
         '0xABCDEF', '1_000', '0o17', '+0x10', '0b', '0x', '  42  ']

if __name__ == '__main__':
    diffs = 0
    print(f"{'input':<12} {'python':<14} {'kotlin':<14} DIFF")
    for t in TESTS:
        try:
            p = python_parse(t)
        except Exception as e:
            p = f"ERR:{type(e).__name__}"
        try:
            k = kotlin_parse(t)
        except Exception as e:
            k = f"ERR:{type(e).__name__}"
        flag = '  <<< DIFF' if str(p) != str(k) else ''
        if str(p) != str(k):
            diffs += 1
        print(f"{repr(t):<12} {str(p):<14} {str(k):<14}{flag}")
    print(f"\n{diffs} differing parses out of {len(TESTS)}")
