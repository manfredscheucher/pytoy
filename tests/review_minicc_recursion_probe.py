"""Check minicc's call-graph cycle detection: reject self/mutual/indirect
recursion, accept a DAG/diamond (no false positive)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pytoy import minicc


def compiles(src):
    try:
        minicc.compile_source(src, "r")
        return True
    except minicc.MiniError:
        return False


def test_self_recursion_rejected():
    assert not compiles("int f(int x){return f(x);} int main(void){return f(1);}")


def test_mutual_recursion_rejected():
    src = ("int a(int x){return b(x);} int b(int x){return a(x);}"
           "int main(void){return a(1);}")
    assert not compiles(src)


def test_indirect_recursion_rejected():
    src = ("int a(int x){return b(x);} int b(int x){return c(x);}"
           "int c(int x){return a(x);} int main(void){return a(1);}")
    assert not compiles(src)


def test_recursion_in_arg_rejected():
    # recursion hidden inside an argument expression
    src = "int f(int x){return f(f(x));} int main(void){return f(1);}"
    assert not compiles(src)


def test_diamond_dag_accepted():
    # main -> g,h ; g -> k ; h -> k ; no cycle. Must compile.
    src = ("int k(int x){return x+1;}"
           "int g(int x){return k(x);}"
           "int h(int x){return k(x);}"
           "int main(void){return g(1)+h(2);}")
    assert compiles(src)


def test_linear_chain_accepted():
    src = ("int c(int x){return x+1;}"
           "int b(int x){return c(x);}"
           "int a(int x){return b(x);}"
           "int main(void){return a(5);}")
    assert compiles(src)


if __name__ == "__main__":
    for n, fn in sorted(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
