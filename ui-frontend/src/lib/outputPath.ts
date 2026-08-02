function suffix(path: string): string {
  const name = path.trim().split(/[\\/]/).at(-1) ?? "";
  const index = name.lastIndexOf(".");
  return index > 0 ? name.slice(index).toLowerCase() : "";
}

export function ensureOutputExtension(path: string, target: string | null): string {
  if (!path.trim() || !target || suffix(path)) return path;
  return `${path}.${target.replace(/^\./, "")}`;
}

export function updateGeneratedExtension(
  path: string,
  previousTarget: string | null,
  nextTarget: string | null,
): string {
  if (!nextTarget) return path;
  const previous = previousTarget ? `.${previousTarget.replace(/^\./, "").toLowerCase()}` : "";
  if (previous && suffix(path) === previous) {
    return `${path.slice(0, -previous.length)}.${nextTarget.replace(/^\./, "")}`;
  }
  return ensureOutputExtension(path, nextTarget);
}

export function outputExtensionWarning(path: string, target: string | null): string | null {
  const actual = suffix(path);
  if (!actual || !target) return null;
  const expected = `.${target.replace(/^\./, "").toLowerCase()}`;
  return actual === expected
    ? null
    : `The output extension ${actual} does not match the selected ${expected} format. The explicit path will be preserved; choose a matching format or path before planning.`;
}
