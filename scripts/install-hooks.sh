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
EOF

chmod +x "$HOOK"
echo "Pre-commit hook installed."
