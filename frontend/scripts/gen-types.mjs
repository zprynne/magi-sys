// Generate src/types/events.generated.ts from the backend's JSON Schema.
//   npm run gen:types          write the file
//   npm run check:types        exit 1 if the file is out of date
import { readFile, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { compileFromFile } from 'json-schema-to-typescript'

const schema = fileURLToPath(new URL('../../schema/magi-events.schema.json', import.meta.url))
const output = fileURLToPath(new URL('../src/types/events.generated.ts', import.meta.url))

const banner = `/* eslint-disable */
/**
 * GENERATED FILE — do not edit by hand.
 * Source: backend/src/magi/events.py -> schema/magi-events.schema.json
 * Regenerate: (cd backend && uv run magi-schema) && (cd frontend && npm run gen:types)
 */`

const ts = await compileFromFile(schema, {
  bannerComment: banner,
  additionalProperties: false,
  unreachableDefinitions: true,
})

if (process.argv.includes('--check')) {
  const current = await readFile(output, 'utf8').catch(() => '')
  if (current !== ts) {
    console.error(`${output} is stale; run \`npm run gen:types\`.`)
    process.exit(1)
  }
  console.log('event types are up to date')
} else {
  await writeFile(output, ts)
  console.log(`wrote ${output}`)
}
