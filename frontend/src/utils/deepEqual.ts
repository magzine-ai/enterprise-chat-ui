/**
 * Deep Equality Utility
 * 
 * A simple deep equality check implementation to replace fast-equals.
 * This is a basic implementation that handles common use cases.
 */

export function deepEqual(a: any, b: any): boolean {
  // Same reference or both null/undefined
  if (a === b) {
    return true;
  }

  // Handle null/undefined cases
  if (a == null || b == null) {
    return a === b;
  }

  // Different types
  if (typeof a !== typeof b) {
    return false;
  }

  // Primitive types
  if (typeof a !== 'object') {
    return a === b;
  }

  // Arrays
  if (Array.isArray(a) && Array.isArray(b)) {
    if (a.length !== b.length) {
      return false;
    }
    for (let i = 0; i < a.length; i++) {
      if (!deepEqual(a[i], b[i])) {
        return false;
      }
    }
    return true;
  }

  // One is array, other is not
  if (Array.isArray(a) || Array.isArray(b)) {
    return false;
  }

  // Objects
  const keysA = Object.keys(a);
  const keysB = Object.keys(b);

  if (keysA.length !== keysB.length) {
    return false;
  }

  for (const key of keysA) {
    if (!keysB.includes(key)) {
      return false;
    }
    if (!deepEqual(a[key], b[key])) {
      return false;
    }
  }

  return true;
}

export function shallowEqual(a: any, b: any): boolean {
  if (a === b) {
    return true;
  }

  if (a == null || b == null) {
    return a === b;
  }

  if (typeof a !== 'object' || typeof b !== 'object') {
    return a === b;
  }

  const keysA = Object.keys(a);
  const keysB = Object.keys(b);

  if (keysA.length !== keysB.length) {
    return false;
  }

  for (const key of keysA) {
    if (a[key] !== b[key]) {
      return false;
    }
  }

  return true;
}

