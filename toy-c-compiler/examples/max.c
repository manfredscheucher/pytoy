// expect: 9
/*
 * max.c - find the maximum of a small fixed set of numbers.
 *
 * Port of examples/max.toy. Arrays are not supported by toycc, so the
 * values 3, 1, 4, 1, 5, 9, 2 are compared pairwise with the '>' operator.
 *
 * max(3, 1, 4, 1, 5, 9, 2) = 9.
 *
 * Expected result: ACC = 9
 */
int main(void) {
    int a = 3;
    int b = 1;
    int c = 4;
    int d = 1;
    int e = 5;
    int f = 9;
    int g = 2;
    int best = a;
    if (b > best) { best = b; }
    if (c > best) { best = c; }
    if (d > best) { best = d; }
    if (e > best) { best = e; }
    if (f > best) { best = f; }
    if (g > best) { best = g; }
    return best;
}
