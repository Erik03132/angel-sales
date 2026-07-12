#!/bin/bash
# Устанавливает pre-commit hook для авто-прогона eval suite Angela
cat > "$(git rev-parse --show-toplevel 2>/dev/null)/.git/hooks/pre-commit" << 'HOOK'
#!/bin/bash
CHANGED=$(git diff --cached --name-only | grep -E "^projects/ai-eggs/agent/angela_agents\.py|^projects/ai-eggs/data/faq_" | head -1)
if [ -z "$CHANGED" ]; then
    exit 0
fi
echo "🔄 Angela files changed — running eval suite..."
cd "$(git rev-parse --show-toplevel)"
python3 projects/ai-eggs/tests/eval_angela.py
RESULT=$?
if [ $RESULT -ne 0 ]; then
    echo ""
    echo "❌ Eval suite FAILED. Fix or commit with --no-verify."
    exit 1
fi
echo "✅ Eval suite passed."
HOOK

chmod +x "$(git rev-parse --show-toplevel 2>/dev/null)/.git/hooks/pre-commit"
echo "✅ Pre-commit hook installed"
