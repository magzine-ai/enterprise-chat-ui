/**
 * Post-install script to replace fast-equals with our custom implementation
 */

const fs = require('fs');
const path = require('path');

const replacementPath = path.resolve(__dirname, '../fast-equals-replacement');
const replacementIndex = path.join(replacementPath, 'index.js');
const replacementTypes = path.join(replacementPath, 'index.d.ts');

// Find all fast-equals installations
const possiblePaths = [
  path.resolve(__dirname, '../node_modules/fast-equals'),
  path.resolve(__dirname, '../node_modules/react-smooth/node_modules/fast-equals'),
];

let replaced = false;

for (const fastEqualsPath of possiblePaths) {
  if (fs.existsSync(fastEqualsPath) && !fs.lstatSync(fastEqualsPath).isSymbolicLink()) {
    console.log(`Replacing fast-equals at ${fastEqualsPath}...`);
    
    // Backup original package.json if it exists
    const originalPackageJson = path.join(fastEqualsPath, 'package.json');
    if (fs.existsSync(originalPackageJson)) {
      fs.copyFileSync(originalPackageJson, originalPackageJson + '.backup');
    }
    
    // Copy our replacement files
    if (fs.existsSync(replacementIndex)) {
      const targetIndex = path.join(fastEqualsPath, 'index.js');
      fs.copyFileSync(replacementIndex, targetIndex);
      console.log('✓ Replaced index.js');
      replaced = true;
    }
    
    if (fs.existsSync(replacementTypes)) {
      const targetTypes = path.join(fastEqualsPath, 'index.d.ts');
      fs.copyFileSync(replacementTypes, targetTypes);
      console.log('✓ Replaced index.d.ts');
    }
  }
}

if (replaced) {
  console.log('✓ fast-equals replacement complete');
} else {
  console.log('⚠ fast-equals not found in expected locations, skipping replacement');
}

