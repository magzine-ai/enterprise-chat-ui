/**
 * Pre-install script to create a stub fast-equals package
 * This prevents npm from trying to download fast-equals from the registry
 */

const fs = require('fs');
const path = require('path');

console.log('🔧 Setting up fast-equals replacement...\n');

const replacementPath = path.resolve(__dirname, '../fast-equals-replacement');
const nodeModulesPath = path.resolve(__dirname, '../node_modules');

// Create node_modules if it doesn't exist
if (!fs.existsSync(nodeModulesPath)) {
  fs.mkdirSync(nodeModulesPath, { recursive: true });
}

// Create a stub fast-equals directory structure
const fastEqualsStubPath = path.join(nodeModulesPath, 'fast-equals');

// If fast-equals already exists, remove it first
if (fs.existsSync(fastEqualsStubPath)) {
  try {
    fs.rmSync(fastEqualsStubPath, { recursive: true, force: true });
  } catch (err) {
    console.log('⚠ Could not remove existing fast-equals, will continue...');
  }
}

// Create the directory
fs.mkdirSync(fastEqualsStubPath, { recursive: true });

// Copy our replacement files
const replacementIndex = path.join(replacementPath, 'index.js');
const replacementTypes = path.join(replacementPath, 'index.d.ts');
const replacementPackage = path.join(replacementPath, 'package.json');

if (fs.existsSync(replacementIndex)) {
  fs.copyFileSync(replacementIndex, path.join(fastEqualsStubPath, 'index.js'));
  console.log('✓ Created fast-equals stub');
}

if (fs.existsSync(replacementTypes)) {
  fs.copyFileSync(replacementTypes, path.join(fastEqualsStubPath, 'index.d.ts'));
}

if (fs.existsSync(replacementPackage)) {
  fs.copyFileSync(replacementPackage, path.join(fastEqualsStubPath, 'package.json'));
}

console.log('✓ fast-equals stub created - npm will use our replacement\n');

