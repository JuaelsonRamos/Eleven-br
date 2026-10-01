export type DateTimeMask = 'date' | 'time' | 'month';

/** Separators appear only when the next digit exists: backspace remains natural. */
export function maskDateTime(value: string, kind: DateTimeMask): string {
  const digits = value.replace(/\D/g, '').slice(0, kind === 'date' ? 8 : kind === 'month' ? 6 : 4);
  const separator = kind === 'time' ? ':' : '/';
  if (digits.length <= 2) return digits;
  const rest = digits.slice(2);
  return digits.slice(0, 2) + separator + (kind === 'date' && rest.length > 2 ? rest.slice(0, 2) + '/' + rest.slice(2) : rest);
}
