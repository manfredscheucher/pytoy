// expect: 55
/*
 * fibonacci.c - compute the n-th Fibonacci number.
 *
 * Port of examples/fibonacci.toy.
 * 8-bit values wrap mod 256, so fib(14) = 377 > 255 overflows.
 * With n = 10, the result is fib(10) = 55.
 *
 * Expected result: ACC = 55
 */
int main(void) {
    int n = 10;
    int a = 0;
    int b = 1;
    while (n != 0) {
        b = a + b;   /* new b = a + old b */
        a = b - a;   /* a = old b */
        n = n - 1;
    }
    return a;
}
