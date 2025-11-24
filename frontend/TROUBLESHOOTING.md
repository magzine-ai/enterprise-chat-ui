# Troubleshooting Guide

## Error: "failed to load url /src/main.tsx pre transform"

This error typically occurs in enterprise environments due to path resolution issues. Here are the solutions:

### Solution 1: Verify File Structure
Ensure the file structure is correct:
```
frontend/
├── index.html
├── src/
│   └── main.tsx
└── vite.config.ts
```

### Solution 2: Clear Cache and Reinstall
```bash
cd frontend
rm -rf node_modules package-lock.json .vite dist
npm install
npm run dev
```

### Solution 3: Check Working Directory
Make sure you're running the command from the `frontend` directory:
```bash
cd enterprise-chat-ui/frontend
npm run dev
```

### Solution 4: Verify Node.js Version
Ensure you're using Node.js 18.0 or higher:
```bash
node --version
```

### Solution 5: Check File Permissions
On enterprise systems, ensure you have read permissions:
```bash
ls -la src/main.tsx
```

### Solution 6: Use Absolute Paths (if needed)
If relative paths don't work, try modifying `vite.config.ts` to use absolute paths.

### Solution 7: Check for Case Sensitivity
On Linux/enterprise systems, file paths are case-sensitive. Ensure:
- `main.tsx` (not `Main.tsx` or `MAIN.tsx`)
- `src/` directory exists

### Solution 8: Verify Vite Configuration
Check that `vite.config.ts` is properly configured with ES module syntax.

### Solution 9: Check Network/Firewall
Enterprise firewalls might block Vite's HMR. Try:
```bash
npm run dev -- --host 0.0.0.0
```

### Solution 10: Check for Special Characters
Ensure no special characters in the path that might cause issues.

## Common Enterprise Issues

1. **Proxy Settings**: Configure npm proxy if behind corporate firewall
2. **SSL Certificates**: May need to configure npm to use corporate certificates
3. **File System Permissions**: Ensure read/write permissions in project directory
4. **Antivirus**: May need to exclude node_modules from scanning

## Getting Help

If none of these solutions work, check:
- Browser console for additional errors
- Terminal output for detailed error messages
- Vite documentation: https://vitejs.dev

