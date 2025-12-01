/**
 * Splunk Query Formatter
 * Formats SPL (Search Processing Language) queries with proper indentation and line breaks
 * to improve readability and prevent horizontal scrolling.
 */

export function formatSplunkQuery(query: string): string {
  if (!query || typeof query !== 'string') {
    return query;
  }

  // Normalize whitespace - replace all whitespace with single spaces
  let normalized = query.trim().replace(/\s+/g, ' ');

  // Simple approach: split by pipes and add line breaks
  // Format: first line, then "| command" on subsequent lines with minimal indent
  const parts = normalized.split(/(?<!\\)\|/).map(p => p.trim()).filter(p => p);
  
  if (parts.length === 0) {
    return query;
  }

  const lines: string[] = [];
  const indentSize = 2;
  const maxLineLength = 100;

  // First part goes on first line (no pipe, no indent)
  lines.push(parts[0]);

  // Remaining parts go on new lines with indent and pipe
  for (let i = 1; i < parts.length; i++) {
    const part = parts[i];
    const indent = ' '.repeat(indentSize);
    const line = indent + '| ' + part;
    
    // Check if line needs wrapping
    if (line.length > maxLineLength && part.includes(' ')) {
      // First line with pipe
      const firstLinePrefix = indent + '| ';
      const firstLineWidth = maxLineLength - firstLinePrefix.length;
      
      let remaining = part;
      let isFirstWrap = true;
      
      while (remaining.length > 0) {
        const wrapIndent = isFirstWrap ? indentSize + 2 : indentSize + 6;
        const wrapPrefix = ' '.repeat(wrapIndent);
        const availableWidth = maxLineLength - wrapPrefix.length;
        
        if (remaining.length <= availableWidth) {
          if (isFirstWrap) {
            lines.push(firstLinePrefix + remaining);
          } else {
            lines.push(wrapPrefix + remaining);
          }
          break;
        }
        
        // Find break point
        let breakPoint = -1;
        for (const bp of [', ', ' AND ', ' OR ', ' ']) {
          const idx = remaining.lastIndexOf(bp, availableWidth);
          if (idx > 0) {
            breakPoint = idx + (bp === ' ' ? 1 : bp.length);
            break;
          }
        }
        
        if (breakPoint > 0) {
          const content = remaining.substring(0, breakPoint).trim();
          if (isFirstWrap) {
            lines.push(firstLinePrefix + content);
          } else {
            lines.push(wrapPrefix + content);
          }
          remaining = remaining.substring(breakPoint).trim();
        } else {
          const content = remaining.substring(0, availableWidth);
          if (isFirstWrap) {
            lines.push(firstLinePrefix + content);
          } else {
            lines.push(wrapPrefix + content);
          }
          remaining = remaining.substring(availableWidth).trim();
        }
        
        isFirstWrap = false;
      }
    } else {
      // Line fits
      lines.push(line);
    }
  }

  return lines.join('\n');
}
