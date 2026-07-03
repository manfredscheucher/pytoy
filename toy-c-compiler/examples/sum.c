// expect: 25
/*
 * sum.c - sum a small fixed set of numbers.
 *
 * Port of examples/sum.toy. Arrays are not supported by toycc (see README),
 * so the values 3, 1, 4, 1, 5, 9, 2 are held in separate int variables.
 *
 * 3 + 1 + 4 + 1 + 5 + 9 + 2 = 25.
 *
 * Expected result: ACC = 25
 */
int main(void) {
    int a = 3;
    int b = 1;
    int c = 4;
    int d = 1;
    int e = 5;
    int f = 9;
    int g = 2;
    return a + b + c + d + e + f + g;
}
