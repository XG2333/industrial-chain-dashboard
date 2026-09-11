import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const { buildClassList } = require('../node_modules/flowbite-react/dist/cli/utils/build-class-list.cjs');
const { COMPONENT_TO_CLASS_LIST_MAP } = require('../node_modules/flowbite-react/dist/metadata/class-list.cjs');

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const srcDir = path.join(root, 'src');
const outputDir = path.join(root, '.flowbite-react');
const outputFile = path.join(outputDir, 'class-list.json');

function walk(dir) {
  const files = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...walk(fullPath));
    } else if (/\.(ts|tsx|js|jsx)$/.test(entry.name)) {
      files.push(fullPath);
    }
  }
  return files;
}

const imported = new Set();
const importRegex = /import\s*\{([^}]*)\}\s*from\s*['"]flowbite-react['"]/g;

for (const file of walk(srcDir)) {
  const content = fs.readFileSync(file, 'utf8');
  let match;
  while ((match = importRegex.exec(content)) !== null) {
    for (const raw of match[1].split(',')) {
      const name = raw.trim().split(/\s+as\s+/)[0]?.trim();
      if (name && name in COMPONENT_TO_CLASS_LIST_MAP) {
        imported.add(name);
      }
    }
  }
}

const components = imported.size > 0 ? [...imported] : ['Card', 'Button', 'Badge', 'Alert'];
const classList = buildClassList({
  components,
  dark: true,
  version: 3,
});

fs.mkdirSync(outputDir, { recursive: true });
fs.writeFileSync(outputFile, JSON.stringify(classList, null, 2));
console.log(`Generated ${outputFile} with ${classList.length} classes`);
