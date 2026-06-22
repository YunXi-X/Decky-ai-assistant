export type TableAlignment = "left" | "center" | "right";

export function normalizeMarkdownTableLine(line: string): string {
  return line.replace(/^\s*(?:>\s*)+/, "").trim();
}

export function splitTableRow(line: string): string[] {
  const trimmed = normalizeMarkdownTableLine(line).replace(/^\|/, "").replace(/\|$/, "");
  return trimmed.split("|").map((cell) => cell.trim());
}

export function isTableSeparator(line: string): boolean {
  const cells = splitTableRow(line);
  return cells.length > 1 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

export function tableAlignments(separatorLine: string): TableAlignment[] {
  return splitTableRow(separatorLine).map((cell) => {
    if (cell.startsWith(":") && cell.endsWith(":")) {
      return "center";
    }
    if (cell.endsWith(":")) {
      return "right";
    }
    return "left";
  });
}

export function isTableStart(lines: string[], index: number): boolean {
  if (index + 1 >= lines.length) {
    return false;
  }
  const header = normalizeMarkdownTableLine(lines[index]);
  const separator = normalizeMarkdownTableLine(lines[index + 1]);
  return header.includes("|") && separator.includes("|") && isTableSeparator(separator);
}
