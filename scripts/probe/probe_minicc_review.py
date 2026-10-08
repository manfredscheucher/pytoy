#!/usr/bin/env python3
"""Ad-hoc probe of pytoy minicc error-message and codegen edge cases, used to
compare against the ktoy MiniCompiler.kt port during review. Run: python3
scripts/probe_minicc_review.py from the pytoy repo root."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pytoy.minicc import compile_source, MiniError

cases = {
    "undefined_fn": "int main(void){ return f(1); }",
    "wrong_arity": "int f(int x){return x;} int main(void){return f(1,2);}",
    "no_main": "int foo(void){return 1;}",
    "recursion": "int f(int x){return f(x);} int main(void){return f(1);}",
    "compound": "int main(void){int x=1; x += 2; return x;}",
    "var_shift": "int main(void){int x=1; int y=2; return x << y;}",
    "unknown_var": "int main(void){return y;}",
    "array_not_scalar": "int main(void){int a[3]; return a;}",
    "scalar_not_array": "int main(void){int x=1; x[0]=1; return x;}",
    "redeclare": "int main(void){int x=1; int x=2; return x;}",
    "too_many_init": "int main(void){int a[1]={1,2}; return a[0];}",
    "main_params": "int main(int x){return x;}",
    "unexpected_char": "int main(void){return @;}",
    "unterminated_comment": "int main(void){ /* oops return 0;}",
    "unexpected_expr": "int main(void){return ;}",
    "eat_mismatch": "int main(void){ int }",
    "expected_got": "int main(void) return 0; }",
}
num_cases = {
    "leading_zero_dec": "int main(void){ return 010; }",
    "big_dec": "int main(void){ return 99999999999999999999999999; }",
    "big_hex": "int main(void){ return 0xFFFFFFFFFFFFFFFFFF; }",
    "dup_func_name": "int f(void){return 1;} int f(void){return 2;} "
                     "int main(void){return f();}",
    "array_size_hex": "int main(void){ int a[0x03]={1,2,3}; return a[2]; }",
    "hex_empty": "int main(void){ return 0x; }",
}
cases.update(num_cases)

# dup function name: does it emit two helper bodies? print the output.
dup = ("int f(void){return 1;} int f(void){return 2;} "
       "int main(void){return f();}")
try:
    out = compile_source(dup, "probe")
    nbody = out.count("__body: nop")
    ndisp = out.count("__dispatch: nop")
    print(f"[dup_detail] bodies={nbody} dispatches={ndisp}")
except Exception as e:
    print(f"[dup_detail] {type(e).__name__}: {e}")

for k, src in cases.items():
    try:
        out = compile_source(src, "probe")
        print(f"[{k}] OK len={len(out)}")
    except MiniError as e:
        print(f"[{k}] MiniError: {e}")
    except Exception as e:
        print(f"[{k}] {type(e).__name__}: {e}")
