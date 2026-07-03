// expect: 12
/*
 * gcd.c - greatest common divisor via the subtraction algorithm.
 *
 * gcd(48, 36): 48-36=12, 36-12=24, 24-12=12, 12-12=0 -> gcd = 12.
 *
 * Demonstrates while, if/else and the '>' comparison.
 *
 * Expected result: ACC = 12
 */
int main(void) {
    int a = 48;
    int b = 36;
    while (a != b) {
        if (a > b) {
            a = a - b;
        } else {
            b = b - a;
        }
    }
    return a;
}
