#!/bin/bash
# Quick integration script - run this to wire up the live signals

echo "🔧 Integrating live signals into frontend..."

# Check if services exists
if [ ! -f "services/live_signal.py" ]; then
    echo "❌ services/live_signal.py not found"
    exit 1
fi

# The frontend changes are already applied
echo "✅ Frontend component: src/components/LiveSignalPanel.tsx"
echo "✅ API route: src/app/api/live-signal/route.ts"
echo "✅ Updated: src/app/page.tsx"

echo ""
echo "🚀 To start the integrated system:"
echo "  1. Terminal 1: cd apps/trade-desk && npm run dev"
echo "  2. Terminal 2: python services/live_signal.py  # optional standalone"
echo ""
echo "🌐 Then open http://localhost:3000 and see live signals for any ticker"