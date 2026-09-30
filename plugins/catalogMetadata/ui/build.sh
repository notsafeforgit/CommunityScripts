#!/bin/sh
set -eu
cd "$(dirname "$0")"
pnpm dlx esbuild@0.28.2 src/index.jsx --outfile=index.js --format=esm --jsx-factory=React.createElement --jsx-fragment=React.Fragment --target=es2022
