// Kanso, by jlopezlira (https://github.com/jlopezlira/herdr-kanso). Apache-2.0.
// This is the source copy; `npm run sync:share` copies it into every mod.

export const range = (n, from = 0) => Array.from({ length: Math.max(0, n) }, (_, i) => from + i);

export const tryOr = (fn, fallback = null) => {
  try { return fn(); } catch { return fallback; }
};
export const tryOrAsync = async (fn, fallback = null) => {
  try { return await fn(); } catch { return fallback; }
};

export const parseOr = (text, fallback = null) => tryOr(() => JSON.parse(text), fallback);

export async function retry(times, fn, { done = Boolean, between = async () => {} } = {}, k = 0) {
  const v = await fn(k);
  if (done(v) || k + 1 >= times) return v;
  await between(k);
  return retry(times, fn, { done, between }, k + 1);
}

export async function findAsync(list, test, i = 0) {
  if (i >= list.length) return null;
  return (await test(list[i], i)) ? list[i] : findAsync(list, test, i + 1);
}

// Halves joined once each, so no list is copied per item and depth stays log n.
export async function mapSeries(list, fn, from = 0, to = list.length) {
  if (to - from <= 0) return [];
  if (to - from === 1) return [await fn(list[from], from)];
  const mid = from + Math.floor((to - from) / 2);
  const left = await mapSeries(list, fn, from, mid);
  return left.concat(await mapSeries(list, fn, mid, to));
}

export async function reduceSeries(list, fn, acc, i = 0) {
  return i >= list.length ? acc : reduceSeries(list, fn, await fn(acc, list[i], i), i + 1);
}
