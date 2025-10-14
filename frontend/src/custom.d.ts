// Allow importing image assets in TypeScript files
declare module '*.png';
declare module '*.jpg';
declare module '*.jpeg';
declare module '*.svg';
declare module '*.gif';

// If you need stricter typing (e.g., returning string URLs), replace with:
// declare module '*.png' { const value: string; export default value; }
