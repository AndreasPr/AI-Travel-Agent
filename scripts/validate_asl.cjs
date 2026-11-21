const fs = require('node:fs');
const validate = require('asl-validator');
const definition = JSON.parse(fs.readFileSync('infra/stepfunctions/deep_plan.asl.json', 'utf8'));
const result = validate(definition);
if (!result.isValid) {
  console.error(result.errorsText('\n'));
  process.exit(1);
}
console.log('ASL definition is valid; not deployed.');
