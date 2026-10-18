// Every inline script in the built page must parse: node .github/scripts/check_page.mjs _site/plot-studio.html
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
const html = readFileSync(process.argv[2] || '_site/plot-studio.html', 'utf8');
let n = 0;
for (const m of html.matchAll(/<script(?![^>]*\bsrc=)(?![^>]*type="application\/json")[^>]*>([\s\S]*?)<\/script>/g)) {
  new vm.Script(m[1], { filename: 'inline-script-' + (++n) });
}
console.log('parsed ' + n + ' inline scripts');
if (!n) process.exit(1);
