import { run } from "herdr";
import { previewTarget } from "./link-target.js";

export function handleLink(click) {
  const target = previewTarget(click);
  if (!target) return "pass";
  run(...target);
  return "handled";
}
