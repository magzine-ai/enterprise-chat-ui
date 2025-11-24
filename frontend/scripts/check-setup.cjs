/**
 * Setup verification script for enterprise environments
 */

const fs = require('fs');
const path = require('path');

console.log('🔍 Checking Enterprise Chat UI setup...\n');

const checks = [
  {
    name: 'Node.js version',
    check: () => {
      const version = process.version;
      const major = parseInt(version.slice(1).split('.')[0]);
      if (major >= 18) {
        return { pass: true, message: `✓ Node.js ${version} (required: >= 18.0)` };
      }
      return { pass: false, message: `✗ Node.js ${version} (required: >= 18.0)` };
    }
  },
  {
    name: 'src/main.tsx exists',
    check: () => {
      const filePath = path.join(__dirname, '../src/main.tsx');
      if (fs.existsSync(filePath)) {
        return { pass: true, message: '✓ src/main.tsx found' };
      }
      return { pass: false, message: '✗ src/main.tsx not found' };
    }
  },
  {
    name: 'index.html exists',
    check: () => {
      const filePath = path.join(__dirname, '../index.html');
      if (fs.existsSync(filePath)) {
        return { pass: true, message: '✓ index.html found' };
      }
      return { pass: false, message: '✗ index.html not found' };
    }
  },
  {
    name: 'vite.config.ts exists',
    check: () => {
      const filePath = path.join(__dirname, '../vite.config.ts');
      if (fs.existsSync(filePath)) {
        return { pass: true, message: '✓ vite.config.ts found' };
      }
      return { pass: false, message: '✗ vite.config.ts not found' };
    }
  },
  {
    name: 'node_modules exists',
    check: () => {
      const dirPath = path.join(__dirname, '../node_modules');
      if (fs.existsSync(dirPath)) {
        return { pass: true, message: '✓ node_modules found' };
      }
      return { pass: false, message: '✗ node_modules not found (run: npm install)' };
    }
  },
  {
    name: 'Working directory',
    check: () => {
      const cwd = process.cwd();
      const expected = path.join(__dirname, '..');
      if (cwd === expected || cwd.includes('frontend')) {
        return { pass: true, message: `✓ Working directory: ${cwd}` };
      }
      return { pass: false, message: `✗ Wrong directory: ${cwd}\n  Expected: ${expected}` };
    }
  }
];

let allPassed = true;

checks.forEach(({ name, check }) => {
  const result = check();
  console.log(`${result.message}`);
  if (!result.pass) {
    allPassed = false;
  }
});

console.log('\n');

if (allPassed) {
  console.log('✅ All checks passed! You can run: npm run dev');
} else {
  console.log('❌ Some checks failed. Please fix the issues above.');
  console.log('\nCommon fixes:');
  console.log('  1. Run: npm install');
  console.log('  2. Ensure you are in the frontend directory');
  console.log('  3. Check file permissions');
}

process.exit(allPassed ? 0 : 1);

