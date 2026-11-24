// The languages a walkthrough can be written in. Only its prose changes: hunk
// aliases, the weight and kind values, and every identifier stay as they are.

export const LANGUAGES = [
  { tag: "en", name: "English", english: "English" },
  { tag: "tr", name: "Türkçe", english: "Turkish" },
  { tag: "de", name: "Deutsch", english: "German" },
  { tag: "fr", name: "Français", english: "French" },
  { tag: "es", name: "Español", english: "Spanish" },
  { tag: "it", name: "Italiano", english: "Italian" },
  { tag: "pt", name: "Português", english: "Portuguese" },
  { tag: "nl", name: "Nederlands", english: "Dutch" },
  { tag: "pl", name: "Polski", english: "Polish" },
  { tag: "uk", name: "Українська", english: "Ukrainian" },
  { tag: "ru", name: "Русский", english: "Russian" },
  { tag: "ja", name: "日本語", english: "Japanese" },
  { tag: "ko", name: "한국어", english: "Korean" },
  { tag: "zh", name: "简体中文", english: "Simplified Chinese" },
];

export const DEFAULT_LANGUAGE = "en";

export const languageOf = (tag) => LANGUAGES.find((l) => l.tag === tag) ?? LANGUAGES[0];

/** "tr-TR", "tr_TR", "pt-BR" → a tag above, or English. */
export function fromLocale(locale) {
  const tag = String(locale ?? "").trim().toLowerCase().split(/[-_.@]/)[0];
  return LANGUAGES.some((l) => l.tag === tag) ? tag : DEFAULT_LANGUAGE;
}
