/** datetime-local has no zone: show a canonical UTC value, never slice an offset string. */
export function utcInput(value:string):string {
  const date=new Date(value);
  return Number.isNaN(date.valueOf())?'':date.toISOString().slice(0,16);
}
export function fromUtcInput(value:string):string {return value?value+':00Z':'';}
