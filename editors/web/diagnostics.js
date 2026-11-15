// Map compiler diagnostics (1-indexed line/column + length, from
// groovescript.web.build) onto CodeMirror document offsets.

const SEVERITIES = new Set(['error', 'warning', 'info']);

/**
 * @param {{ lines: number, line(n: number): { from: number, to: number, text?: string } }} doc
 *   A CodeMirror `Text` (or anything with the same shape).
 * @param {Array<{ severity: string, message: string, hint?: string | null,
 *                 line?: number | null, column?: number | null,
 *                 length?: number }>} diags
 * @returns {Array<{ from: number, to: number, severity: string, message: string }>}
 */
export function toEditorDiagnostics(doc, diags) {
  const out = [];
  for (const d of diags) {
    const severity = SEVERITIES.has(d.severity) ? d.severity : 'error';
    const message = d.hint ? `${d.message}\nhint: ${d.hint}` : d.message;
    let from = 0;
    let to = 0;
    if (d.line != null && doc.lines > 0) {
      const ln = doc.line(Math.min(Math.max(d.line, 1), doc.lines));
      if (d.column != null) {
        // The compiler counts code points; CodeMirror offsets count UTF-16
        // units, so characters outside the BMP (emoji) take two.
        const startCp = Math.max(d.column, 1) - 1;
        const lenCp = Math.max(d.length ?? 1, 1);
        from = Math.min(ln.from + utf16Offset(ln.text, startCp), ln.to);
        to = Math.min(ln.from + utf16Offset(ln.text, startCp + lenCp), ln.to);
      } else {
        // No column: underline the line's text, skipping indentation.
        from = ln.from;
        to = ln.to;
      }
      if (to <= from) to = Math.min(from + 1, ln.to);
      if (to <= from && from > ln.from) from -= 1; // empty tail: mark the last char
    }
    out.push({ from, to, severity, message });
  }
  return out;
}

/** UTF-16 length of the first ``cp`` code points of ``text`` (``cp`` when
 * the line text is unavailable). */
function utf16Offset(text, cp) {
  if (typeof text !== 'string') return cp;
  let units = 0;
  let seen = 0;
  for (const ch of text) {
    if (seen === cp) return units;
    units += ch.length;
    seen += 1;
  }
  return units + (cp - seen); // past the end: clamped by the caller
}

/**
 * One-line summary for the problems bar.
 * @param {Array<{ severity: string, message: string, hint?: string | null, line?: number | null }>} diags
 * @returns {{ level: 'ok' | 'error' | 'warning' | 'info', text: string, first: object | null }}
 */
export function summarize(diags) {
  const order = ['error', 'warning', 'info'];
  for (const level of order) {
    const hits = diags.filter((d) => d.severity === level);
    if (!hits.length) continue;
    const first = hits[0];
    const where = first.line != null ? `line ${first.line}: ` : '';
    const more = hits.length > 1 ? ` (+${hits.length - 1} more)` : '';
    const hint = first.hint ? ` — ${first.hint}` : '';
    return { level, text: `${where}${first.message}${hint}${more}`, first };
  }
  return { level: 'ok', text: 'No problems', first: null };
}
