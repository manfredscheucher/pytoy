// expect: 36
/*
 * bitops.c - showcase the bitwise operators and shifts, which map directly
 * to Toy CPU opcodes (and, or, xor, not, left, right).
 *
 *   x    = 0xF0            = 11110000
 *   y    = 0x3C            = 00111100
 *   a = x & y             = 00110000 = 0x30 = 48
 *   b = x | y             = 11111100 = 0xFC = 252
 *   c = x ^ y             = 11001100 = 0xCC = 204
 *   a = a >> 2            = 00001100 = 12
 *   a = a << 1            = 00011000 = 24
 *   result = a + (c & 0x0F)   c & 0x0F = 00001100 = 12; 24 + 12 = 36
 *
 * Expected result: ACC = 36
 */
int main(void) {
    int x = 0xF0;
    int y = 0x3C;
    int a = x & y;
    int c = x ^ y;
    a = a >> 2;
    a = a << 1;
    return a + (c & 0x0F);
}
