#!/bin/bash
# Install git pre-commit hook that runs pytest before each commit.

HOOK=".git/hooks/pre-commit"

if [ ! -d .git ]; then
    echo "Error: not in a git repository root"
    exit 1
fi

mkdir -p .git/hooks

cat > "$HOOK" << 'EOF'
#!/bin/bash
echo "Running tests..."
python3 -m pytest tests/ -q --tb=short
if [ $? -ne 0 ]; then
    echo ""
    echo "Tests failed — commit aborted."
    echo "Use 'git commit --no-verify' to skip."
    exit 1
fi

# Keep ktoy's embedded examples in sync with examples/. The .toys/.toyo sources
# here are the single source of truth; ktoy/ExampleSources.kt is generated from
# them. If examples changed but ExampleSources.kt wasn't regenerated + committed,
# the two would drift — so regenerate and abort if it now differs.
KTOY_GEN="$HOME/github/ktoy/composeApp/src/commonMain/kotlin/org/bytefred/ktoy/core/ExampleSources.kt"
if git diff --cached --name-only | grep -q '^examples/'; then
    if [ -f "$KTOY_GEN" ]; then
        before=$(cat "$KTOY_GEN")
        python3 scripts/gen_ktoy_examples.py >/dev/null
        after=$(cat "$KTOY_GEN")
        if [ "$before" != "$after" ]; then
            echo ""
            echo "examples/ changed but ktoy ExampleSources.kt was stale."
            echo "It has been regenerated — review and commit it in the ktoy repo,"
            echo "then commit here again. (git commit --no-verify to skip.)"
            exit 1
        fi
    fi
fi
EOF

chmod +x "$HOOK"
echo "Pre-commit hook installed."
