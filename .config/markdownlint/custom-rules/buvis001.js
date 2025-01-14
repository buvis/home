/**
 * @type {import("markdownlint").Rule}
 */
module.exports = {
  names: ["BUVIS001"],
  description: "Sublist indentation",
  tags: ["lists", "indentation"],
  function: (params, onError) => {
    const DEFAULT_INDENT = 4;
    const indent = params.config.indent || DEFAULT_INDENT;

    const listItemRegex = /^(\s*)([-+*]|\d+\.)\s+/;
    const listStack = [];

    params.lines.forEach((line, lineIndex) => {
      const match = line.match(listItemRegex);
      if (!match) return;

      const [_, indentSpaces, marker] = match;
      const currentIndent = indentSpaces.length;

      adjustStack(listStack, currentIndent);

      if (listStack.length > 0) {
        validateIndentation(
          listStack[listStack.length - 1],
          currentIndent,
          indent,
          line,
          lineIndex,
          onError,
        );
      }

      listStack.push({
        type: isOrderedList(marker) ? "ordered" : "unordered",
        indent: currentIndent,
      });
    });
  },
};

/**
 * Adjusts the stack by removing elements with indentation greater than or equal to the current level.
 * @param {Array} stack - The list stack.
 * @param {number} currentIndent - The current item's indentation level.
 */
function adjustStack(stack, currentIndent) {
  while (stack.length > 0 && currentIndent <= stack[stack.length - 1].indent) {
    stack.pop();
  }
}

/**
 * Validates the indentation of a nested list item and reports an error if it doesn't match the expected level.
 * @param {Object} parent - The parent list item.
 * @param {number} currentIndent - The current item's indentation level.
 * @param {number} indent - The configured indentation level.
 * @param {string} line - The current line being processed.
 * @param {number} lineIndex - The index of the current line.
 * @param {Function} onError - The callback for reporting errors.
 */
function validateIndentation(
  parent,
  currentIndent,
  indent,
  line,
  lineIndex,
  onError,
) {
  const expectedIndent = parent.indent + indent;

  if (currentIndent !== expectedIndent) {
    onError({
      lineNumber: lineIndex + 1,
      detail: `Nested list must be indented exactly ${indent} spaces from parent list item (${expectedIndent} spaces total). Found ${currentIndent} spaces.`,
      context: line,
      fixInfo: {
        editColumn: 1,
        deleteCount: currentIndent,
        insertText: " ".repeat(expectedIndent),
      },
    });
  }
}

/**
 * Determines if a marker represents an ordered list.
 * @param {string} marker - The list marker (e.g., "-", "*", or "1.").
 * @returns {boolean} True if the marker is for an ordered list; otherwise, false.
 */
function isOrderedList(marker) {
  return /^\d+\./.test(marker);
}
