/**
 * Type definitions for fast-equals replacement
 */

export declare function deepEqual(a: any, b: any): boolean;
export declare function shallowEqual(a: any, b: any): boolean;
export declare function circularDeepEqual(a: any, b: any): boolean;
export declare function circularShallowEqual(a: any, b: any): boolean;
export declare function strictEqual(a: any, b: any): boolean;
export declare function sameValueZeroEqual(a: any, b: any): boolean;

declare const _default: {
  deepEqual: typeof deepEqual;
  shallowEqual: typeof shallowEqual;
  circularDeepEqual: typeof circularDeepEqual;
  circularShallowEqual: typeof circularShallowEqual;
  strictEqual: typeof strictEqual;
  sameValueZeroEqual: typeof sameValueZeroEqual;
};

export default _default;

