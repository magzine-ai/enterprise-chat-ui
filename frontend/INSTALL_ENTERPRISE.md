# Enterprise Installation Guide

## Problem: fast-equals 403 Forbidden Error

If you're seeing a `403 Forbidden` error when trying to install `fast-equals` from your corporate npm registry, this guide will help you work around it.

## Quick Solution: Use Installation Scripts

### For Windows:
```bash
install-enterprise.bat
```

### For Linux/Mac:
```bash
chmod +x install-enterprise.sh
./install-enterprise.sh
```

These scripts will:
1. Install dependencies while ignoring scripts (to avoid fast-equals error)
2. Manually set up the fast-equals replacement
3. Run postinstall to verify everything is correct

## Manual Installation Steps (if scripts don't work)

### Step 1: Install Dependencies (Skip fast-equals)

```bash
cd frontend
npm install --ignore-scripts
```

This will install all dependencies except run scripts. The `fast-equals` error will be ignored.

### Step 2: Manually Create fast-equals Stub

```bash
# Create the directory structure
mkdir -p node_modules/fast-equals

# Copy our replacement files
cp fast-equals-replacement/index.js node_modules/fast-equals/
cp fast-equals-replacement/index.d.ts node_modules/fast-equals/
cp fast-equals-replacement/package.json node_modules/fast-equals/
```

### Step 3: Install react-smooth's fast-equals Dependency

```bash
# Create nested directory for react-smooth
mkdir -p node_modules/react-smooth/node_modules/fast-equals

# Copy replacement files there too
cp fast-equals-replacement/index.js node_modules/react-smooth/node_modules/fast-equals/
cp fast-equals-replacement/index.d.ts node_modules/react-smooth/node_modules/fast-equals/
cp fast-equals-replacement/package.json node_modules/react-smooth/node_modules/fast-equals/
```

### Step 4: Verify Installation

```bash
# Check if files exist
ls -la node_modules/fast-equals/
ls -la node_modules/react-smooth/node_modules/fast-equals/

# Run the replacement script to ensure everything is correct
npm run postinstall
```

### Step 5: Start Development Server

```bash
npm run dev
```

## Alternative: Use npm overrides (if supported)

If your npm version supports overrides, you can add this to `package.json`:

```json
{
  "overrides": {
    "fast-equals": "file:./fast-equals-replacement"
  }
}
```

However, this may not work with all npm versions or corporate registries.

## Windows PowerShell Script

For Windows users, create a file `install-enterprise.ps1`:

```powershell
# Create directories
New-Item -ItemType Directory -Force -Path "node_modules\fast-equals"
New-Item -ItemType Directory -Force -Path "node_modules\react-smooth\node_modules\fast-equals"

# Copy files
Copy-Item "fast-equals-replacement\*" -Destination "node_modules\fast-equals\" -Recurse
Copy-Item "fast-equals-replacement\*" -Destination "node_modules\react-smooth\node_modules\fast-equals\" -Recurse

Write-Host "✓ fast-equals replacement installed"
```

Then run:
```powershell
npm install --ignore-scripts
.\install-enterprise.ps1
npm run postinstall
```

## Troubleshooting

### If npm install still fails:

1. **Clear npm cache:**
   ```bash
   npm cache clean --force
   ```

2. **Remove node_modules and package-lock.json:**
   ```bash
   rm -rf node_modules package-lock.json
   ```

3. **Try installing with different flags:**
   ```bash
   npm install --legacy-peer-deps --ignore-scripts
   ```

4. **Check npm registry configuration:**
   ```bash
   npm config get registry
   ```

### If you still see fast-equals errors:

The replacement files are in `fast-equals-replacement/`. You can manually copy them to wherever npm expects `fast-equals` to be.

## Verification

After installation, verify the replacement worked:

```bash
# Check the content of fast-equals
head -5 node_modules/react-smooth/node_modules/fast-equals/index.js
```

You should see:
```
/**
 * fast-equals replacement
 * 
 * This is a drop-in replacement for fast-equals that uses a simple
 * deep equality implementation instead of the fast-equals library.
```

If you see this, the replacement is working correctly!

