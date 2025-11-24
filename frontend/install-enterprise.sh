#!/bin/bash
# Enterprise Installation Script for Linux/Mac
# This script installs dependencies and sets up fast-equals replacement

echo "Installing Enterprise Chat UI..."
echo ""

# Step 1: Install dependencies (skip scripts to avoid fast-equals error)
echo "Step 1: Installing dependencies (ignoring scripts)..."
npm install --ignore-scripts || echo "Warning: Some packages may have failed, continuing..."

echo ""
echo "Step 2: Setting up fast-equals replacement..."

# Create directories
mkdir -p node_modules/fast-equals
mkdir -p node_modules/react-smooth/node_modules/fast-equals

# Copy replacement files
if [ -f "fast-equals-replacement/index.js" ]; then
    cp fast-equals-replacement/index.js node_modules/fast-equals/
    cp fast-equals-replacement/index.js node_modules/react-smooth/node_modules/fast-equals/
    echo "  [OK] Copied index.js"
fi

if [ -f "fast-equals-replacement/index.d.ts" ]; then
    cp fast-equals-replacement/index.d.ts node_modules/fast-equals/
    cp fast-equals-replacement/index.d.ts node_modules/react-smooth/node_modules/fast-equals/
    echo "  [OK] Copied index.d.ts"
fi

if [ -f "fast-equals-replacement/package.json" ]; then
    cp fast-equals-replacement/package.json node_modules/fast-equals/
    cp fast-equals-replacement/package.json node_modules/react-smooth/node_modules/fast-equals/
    echo "  [OK] Copied package.json"
fi

echo ""
echo "Step 3: Running postinstall script..."
npm run postinstall

echo ""
echo "========================================"
echo "Installation complete!"
echo "========================================"
echo ""
echo "You can now run: npm run dev"
echo ""

