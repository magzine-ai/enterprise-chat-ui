/**
 * Splunk Query Formatter
 * Formats SPL (Search Processing Language) queries with proper indentation and line breaks
 * to improve readability and prevent horizontal scrolling.
 */

export function formatSplunkQuery(query: string): string {
  if (!query || typeof query !== 'string') {
    return query;
  }

  // Normalize whitespace first
  let formatted = query.trim().replace(/\s+/g, ' ');

  // Split by pipe operators (|) - the main separator in SPL
  const segments: string[] = [];
  let currentSegment = '';
  
  for (let i = 0; i < formatted.length; i++) {
    const char = formatted[i];
    const prevChar = i > 0 ? formatted[i - 1] : '';
    
    // Check if this is a pipe operator (not inside quotes)
    if (char === '|' && prevChar !== '\\') {
      if (currentSegment.trim()) {
        segments.push(currentSegment.trim());
      }
      segments.push('|');
      currentSegment = '';
    } else {
      currentSegment += char;
    }
  }
  
  if (currentSegment.trim()) {
    segments.push(currentSegment.trim());
  }

  // Build formatted output with proper line breaks and indentation
  const lines: string[] = [];
  const indentSize = 2;
  let currentIndent = 0;
  const maxLineLength = 100;

  for (let i = 0; i < segments.length; i++) {
    const segment = segments[i];
    
    if (segment === '|') {
      // Start new line with pipe and increase indent for next line
      lines.push(' '.repeat(currentIndent) + '|');
      currentIndent += indentSize;
    } else {
      // Add the command/expression
      const linePrefix = ' '.repeat(currentIndent);
      const availableWidth = maxLineLength - currentIndent;
      
      // If segment is too long, wrap it
      if (segment.length > availableWidth && segment.includes(' ')) {
        let remaining = segment;
        let isFirstLine = true;
        
        while (remaining.length > 0) {
          const indent = isFirstLine ? currentIndent : currentIndent + 4;
          const width = maxLineLength - indent;
          
          if (remaining.length <= width) {
            lines.push(' '.repeat(indent) + remaining);
            break;
          }
          
          // Try to break at logical points: commas, AND, OR, or spaces
          let breakPoint = -1;
          const breakPoints = [', ', ' AND ', ' OR ', ' '];
          
          for (const bp of breakPoints) {
            const idx = remaining.lastIndexOf(bp, width);
            if (idx > 0) {
              breakPoint = idx + (bp === ' ' ? 1 : bp.length);
              break;
            }
          }
          
          if (breakPoint > 0) {
            lines.push(' '.repeat(indent) + remaining.substring(0, breakPoint).trim());
            remaining = remaining.substring(breakPoint).trim();
          } else {
            // Force break at width
            lines.push(' '.repeat(indent) + remaining.substring(0, width));
            remaining = remaining.substring(width).trim();
          }
          
          isFirstLine = false;
        }
      } else {
        // Segment fits on one line
        lines.push(linePrefix + segment);
      }
    }
  }

  return lines.join('\n');
}

