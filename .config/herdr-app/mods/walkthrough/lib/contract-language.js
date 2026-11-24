import { LANGUAGES, fromLocale } from "./languages.js";

const keys = ['before', 'after', 'absent', 'removed', 'impact', 'rollout', 'noRollout', 'showSource', 'hideSource', 'stale', 'contracts'];
const entry = (database, compatibility, operations, labels) => ({
  kinds: { database, protobuf: 'Protobuf', api: 'API' },
  compatibility: Object.fromEntries(['additive', 'breaking', 'mixed', 'unknown'].map((key, i) => [key, compatibility.split('|')[i]])),
  operations: Object.fromEntries(['added', 'removed', 'modified'].map((key, i) => [key, operations.split('|')[i]])),
  ...Object.fromEntries(keys.map((key, i) => [key, labels.split('|')[i]])),
});
export const CONTRACT_TRANSLATIONS = {
  en: entry('Database', 'Additive change|Breaking change|Mixed changes|Compatibility unknown', 'Added|Removed|Modified',
    'Before|After|Did not exist|Removed|Compatibility impact|Deployment order|Deployment order is not established by the diff.|Show source diff|Hide source diff|{count} source fragment(s) changed since this report was generated. Regenerate to update the comparisons.|Contracts'),
  pl: entry('Baza danych', 'Zmiana addytywna|Zmiana niekompatybilna|Zmiany mieszane|Zgodność nieustalona', 'Dodano|Usunięto|Zmieniono',
    'Przed zmianą|Po zmianie|Nie istniało|Usunięto|Wpływ na zgodność|Kolejność wdrożenia|Kolejność wdrożenia nie została ustalona na podstawie diffu.|Pokaż źródłowy diff|Ukryj źródłowy diff|{count} fragmentów źródła zmieniło się od utworzenia raportu. Wygeneruj go ponownie, aby zaktualizować porównania.|Kontrakty'),
  tr: entry('Veritabanı', 'Eklemeli değişiklik|Uyumsuz değişiklik|Karma değişiklikler|Uyumluluk bilinmiyor', 'Eklendi|Kaldırıldı|Değiştirildi',
    'Önce|Sonra|Mevcut değildi|Kaldırıldı|Uyumluluk etkisi|Dağıtım sırası|Dağıtım sırası diff üzerinden belirlenemedi.|Kaynak diff’i göster|Kaynak diff’i gizle|Rapor oluşturulduktan sonra {count} kaynak parçası değişti. Karşılaştırmaları güncellemek için yeniden oluşturun.|Sözleşmeler'),
  de: entry('Datenbank', 'Additive Änderung|Inkompatible Änderung|Gemischte Änderungen|Kompatibilität unbekannt', 'Hinzugefügt|Entfernt|Geändert',
    'Vorher|Nachher|Nicht vorhanden|Entfernt|Auswirkung auf die Kompatibilität|Bereitstellungsreihenfolge|Die Bereitstellungsreihenfolge geht nicht aus dem Diff hervor.|Quell-Diff anzeigen|Quell-Diff ausblenden|Seit der Berichterstellung haben sich {count} Quellfragmente geändert. Bericht neu erstellen, um die Vergleiche zu aktualisieren.|Schnittstellenverträge'),
  fr: entry('Base de données', 'Modification additive|Modification incompatible|Modifications mixtes|Compatibilité inconnue', 'Ajouté|Supprimé|Modifié',
    'Avant|Après|N’existait pas|Supprimé|Impact sur la compatibilité|Ordre de déploiement|Le diff ne permet pas de déterminer l’ordre de déploiement.|Afficher le diff source|Masquer le diff source|{count} fragments source ont changé depuis la génération du rapport. Régénérez-le pour actualiser les comparaisons.|Contrats'),
  es: entry('Base de datos', 'Cambio aditivo|Cambio incompatible|Cambios mixtos|Compatibilidad desconocida', 'Añadido|Eliminado|Modificado',
    'Antes|Después|No existía|Eliminado|Impacto en la compatibilidad|Orden de despliegue|El diff no permite determinar el orden de despliegue.|Mostrar diff de origen|Ocultar diff de origen|{count} fragmentos de origen han cambiado desde que se generó el informe. Genérelo de nuevo para actualizar las comparaciones.|Contratos'),
  it: entry('Database', 'Modifica additiva|Modifica incompatibile|Modifiche miste|Compatibilità sconosciuta', 'Aggiunto|Rimosso|Modificato',
    'Prima|Dopo|Non esisteva|Rimosso|Impatto sulla compatibilità|Ordine di distribuzione|L’ordine di distribuzione non è determinabile dal diff.|Mostra diff sorgente|Nascondi diff sorgente|{count} frammenti sorgente sono cambiati dalla generazione del rapporto. Rigeneralo per aggiornare i confronti.|Contratti'),
  pt: entry('Base de dados', 'Alteração aditiva|Alteração incompatível|Alterações mistas|Compatibilidade desconhecida', 'Adicionado|Removido|Modificado',
    'Antes|Depois|Não existia|Removido|Impacto na compatibilidade|Ordem de implantação|O diff não permite determinar a ordem de implantação.|Mostrar diff de origem|Ocultar diff de origem|{count} fragmentos de origem mudaram desde a geração do relatório. Gere-o novamente para atualizar as comparações.|Contratos'),
  nl: entry('Database', 'Additieve wijziging|Incompatibele wijziging|Gemengde wijzigingen|Compatibiliteit onbekend', 'Toegevoegd|Verwijderd|Gewijzigd',
    'Voor|Na|Bestond niet|Verwijderd|Gevolgen voor compatibiliteit|Uitrolvolgorde|De uitrolvolgorde kan niet uit de diff worden afgeleid.|Bron-diff tonen|Bron-diff verbergen|{count} bronfragmenten zijn gewijzigd sinds het rapport is gegenereerd. Genereer het opnieuw om de vergelijkingen bij te werken.|Contracten'),
  uk: entry('База даних', 'Адитивна зміна|Несумісна зміна|Змішані зміни|Сумісність невідома', 'Додано|Видалено|Змінено',
    'До зміни|Після зміни|Не існувало|Видалено|Вплив на сумісність|Порядок розгортання|Порядок розгортання не встановлено на основі diff.|Показати вихідний diff|Приховати вихідний diff|Після створення звіту змінилося {count} фрагментів джерела. Створіть звіт знову, щоб оновити порівняння.|Контракти'),
  ru: entry('База данных', 'Аддитивное изменение|Несовместимое изменение|Смешанные изменения|Совместимость неизвестна', 'Добавлено|Удалено|Изменено',
    'До изменения|После изменения|Не существовало|Удалено|Влияние на совместимость|Порядок развёртывания|Порядок развёртывания не установлен на основе diff.|Показать исходный diff|Скрыть исходный diff|После создания отчёта изменилось {count} фрагментов источника. Создайте отчёт заново, чтобы обновить сравнения.|Контракты'),
  ja: entry('データベース', '追加変更|互換性のない変更|複合的な変更|互換性は不明', '追加|削除|変更',
    '変更前|変更後|存在しませんでした|削除済み|互換性への影響|デプロイ順序|差分からデプロイ順序を特定できません。|ソース差分を表示|ソース差分を非表示|レポート生成後に{count}個のソース断片が変更されました。比較を更新するには再生成してください。|コントラクト'),
  ko: entry('데이터베이스', '추가 변경|호환되지 않는 변경|혼합 변경|호환성 알 수 없음', '추가됨|삭제됨|수정됨',
    '변경 전|변경 후|존재하지 않았음|삭제됨|호환성 영향|배포 순서|차이점에서 배포 순서를 확인할 수 없습니다.|소스 차이점 표시|소스 차이점 숨기기|보고서 생성 후 소스 조각 {count}개가 변경되었습니다. 비교를 업데이트하려면 다시 생성하세요.|계약'),
  zh: entry('数据库', '增量变更|不兼容变更|混合变更|兼容性未知', '已添加|已删除|已修改',
    '变更前|变更后|原先不存在|已删除|兼容性影响|部署顺序|无法根据差异确定部署顺序。|显示源代码差异|隐藏源代码差异|报告生成后有{count}个源代码片段发生变化。请重新生成以更新比较。|接口契约'),
};

// Controls for per-change evidence share the selected contract language.
const evidenceTranslations = {
  en: ['Go to step: {title}', 'No walkthrough step explains this change.', 'Source evidence is no longer available. Regenerate this report.'],
  pl: ['Przejdź do kroku: {title}', 'Żaden krok raportu nie wyjaśnia tej zmiany.', 'Źródło tej zmiany nie jest już dostępne. Wygeneruj raport ponownie.'],
  tr: ['Adıma git: {title}', 'Bu değişikliği açıklayan bir adım yok.', 'Kaynak kanıtı artık mevcut değil. Raporu yeniden oluşturun.'],
  de: ['Zum Schritt: {title}', 'Kein Berichtsschritt erklärt diese Änderung.', 'Der Quellnachweis ist nicht mehr verfügbar. Bericht neu erstellen.'],
  fr: ['Aller à l’étape : {title}', 'Aucune étape du rapport n’explique cette modification.', 'La source justificative n’est plus disponible. Régénérez le rapport.'],
  es: ['Ir al paso: {title}', 'Ningún paso del informe explica este cambio.', 'La evidencia de origen ya no está disponible. Genere el informe de nuevo.'],
  it: ['Vai al passaggio: {title}', 'Nessun passaggio del rapporto spiega questa modifica.', 'La fonte non è più disponibile. Rigenera il rapporto.'],
  pt: ['Ir para a etapa: {title}', 'Nenhuma etapa do relatório explica esta alteração.', 'A evidência de origem já não está disponível. Gere o relatório novamente.'],
  nl: ['Ga naar stap: {title}', 'Geen stap in het rapport legt deze wijziging uit.', 'Het bronbewijs is niet meer beschikbaar. Genereer het rapport opnieuw.'],
  uk: ['Перейти до кроку: {title}', 'Жоден крок звіту не пояснює цю зміну.', 'Джерело підтвердження більше недоступне. Створіть звіт знову.'],
  ru: ['Перейти к шагу: {title}', 'Ни один шаг отчёта не объясняет это изменение.', 'Исходное подтверждение больше недоступно. Создайте отчёт заново.'],
  ja: ['手順へ移動: {title}', 'この変更を説明する手順はありません。', '根拠となるソースは利用できません。レポートを再生成してください。'],
  ko: ['단계로 이동: {title}', '이 변경을 설명하는 보고서 단계가 없습니다.', '근거 소스를 더 이상 사용할 수 없습니다. 보고서를 다시 생성하세요.'],
  zh: ['跳转到步骤：{title}', '没有报告步骤解释此变更。', '依据源代码已不可用。请重新生成报告。'],
};
for (const [tag, values] of Object.entries(evidenceTranslations)) {
  Object.assign(CONTRACT_TRANSLATIONS[tag], Object.fromEntries(['goToStep', 'noStep', 'noSource'].map((key, i) => [key, values[i]])));
}

/** Accept saved tags, locale tags and existing human-readable export metadata. */
export function contractStrings(language = 'en') {
  const value = String(language ?? '').trim();
  const match = LANGUAGES.find((l) => [l.tag, l.name, l.english].some((s) => s.toLowerCase() === value.toLowerCase()));
  return CONTRACT_TRANSLATIONS[match?.tag ?? fromLocale(value)] ?? CONTRACT_TRANSLATIONS.en;
}

