/**
 * Post-install script to replace fast-equals with our custom implementation
 */

const fs = require('fs');
const path = require('path');

const fastEqualsPath = path.join(__dirname, '../node_modules/fast-equals');
const replacementPath = path.join(__dirname, '../fast-equals-replacement');

if (fs.existsSync(fastEqualsPath)) {
  console.log('Replacing fast-equals with custom implementation...');
  
  // Backup original package.json
  const originalPackageJson = path.join(fastEqualsPath, 'package.json');
  if (fs.existsSync(originalPackageJson)) {
    fs.copyFileSync(originalPackageJson, originalPackageJson + '.backup');
  }
  
  // Copy our replacement files
  const replacementIndex = path.join(replacementPath, 'index.js');
  const replacementTypes = path.join(replacementPath, 'index.d.ts');
  
  if (fs.existsSync(replacementIndex)) {
    // Replace the main index file
    const targetIndex = path.join(fastEqualsPath, 'index.js');
    fs.copyFileSync(replacementIndex, targetIndex);
    console.log('✓ Replaced index.js');
  }
  
  if (fs.existsSync(replacementTypes)) {
    // Replace type definitions if they exist
    const targetTypes = path.join(fastEqualsPath, 'index.d.ts');
    if (fs.existsSync(targetTypes)) {
      fs.copyFileSync(replacementTypes, targetTypes);
      console.log('✓ Replaced index.d.ts');
    }
  }
  
  console.log('✓ fast-equals replacement complete');
} else {
  console.log('fast-equals not found, skipping replacement');
}

