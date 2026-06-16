declare module 'react/jsx-runtime' {
  export * from 'react';
}

declare namespace JSX {
  interface IntrinsicElements {
    [elemName: string]: any;
  }
}
