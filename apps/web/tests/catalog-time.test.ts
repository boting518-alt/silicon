import {test} from 'node:test';
import assert from 'node:assert/strict';
import {utcInput,fromUtcInput} from '../src/catalogTime.ts';
test('editing an offset price timestamp keeps the UTC instant',()=>{
  const original='2026-01-01T08:00:00+08:00';
  assert.equal(utcInput(original),'2026-01-01T00:00');
  assert.equal(new Date(fromUtcInput(utcInput(original))).valueOf(),new Date(original).valueOf());
});
test('UTC input preserves the half-open boundary across negative offsets',()=>{
  assert.equal(utcInput('2026-12-31T19:00:00-05:00'),'2027-01-01T00:00');
});
test('clearing the date field does not crash the editor',()=>{
  assert.equal(utcInput(''),'');assert.equal(fromUtcInput(''),'');
});
