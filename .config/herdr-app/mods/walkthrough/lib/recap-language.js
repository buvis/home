// The Recap page's and its Markdown's own words, in every language a report
// can be written in, so a report reads in one language throughout. Component
// status reuses the contracts' Added/Modified, so the two never disagree.
import { contractStrings } from "./contract-language.js";

const KEYS = [
  "recap", "change", "motivation", "files", "other", "architecture", "components", "groups", "context",
  "changesAndMotivations", "componentDetails", "whatChanged", "sourceFiles", "close", "showAll", "selectComponent",
  "leftOut", "noBlueprint",
];

const TABLE = {
  en: "Recap|Change|Motivation|Files|Other changes|Architecture|Components|Architecture groups|Context|Changes and motivations|Component details|What changed|Source files|Close|Show all|Select a component on the blueprint to inspect its role and source changes.|Left out {count} detail(s) of the recap, blueprint or contracts that didn't match the diff. Regenerate to try again.|No blueprint: the model's diagram couldn't be drawn.",
  tr: "Özet|Değişiklik|Gerekçe|Dosyalar|Diğer değişiklikler|Mimari|Bileşenler|Mimari gruplar|Bağlam|Değişiklikler ve gerekçeleri|Bileşen ayrıntıları|Ne değişti|Kaynak dosyalar|Kapat|Tümünü göster|Rolünü ve kaynak değişikliklerini incelemek için şemada bir bileşen seçin.|Özet, şema veya sözleşmelerdeki {count} ayrıntı diff ile eşleşmediği için atlandı. Yeniden denemek için yeniden üretin.|Şema yok: modelin diyagramı çizilemedi.",
  de: "Zusammenfassung|Änderung|Motivation|Dateien|Weitere Änderungen|Architektur|Komponenten|Architekturgruppen|Kontext|Änderungen und Motivation|Komponentendetails|Was sich geändert hat|Quelldateien|Schließen|Alle anzeigen|Wählen Sie eine Komponente im Bauplan, um ihre Rolle und Quelländerungen zu sehen.|{count} Detail(s) aus Zusammenfassung, Bauplan oder Schnittstellenverträgen passten nicht zum Diff und wurden ausgelassen. Neu erzeugen, um es erneut zu versuchen.|Kein Bauplan: Das Diagramm des Modells konnte nicht gezeichnet werden.",
  fr: "Récapitulatif|Changement|Motivation|Fichiers|Autres changements|Architecture|Composants|Groupes d’architecture|Contexte|Changements et motivations|Détails du composant|Ce qui a changé|Fichiers source|Fermer|Tout afficher|Sélectionnez un composant sur le plan pour voir son rôle et ses changements de source.|Détails du récapitulatif, du plan ou des contrats non conformes au diff, omis : {count}. Régénérez pour réessayer.|Pas de plan : le diagramme du modèle n’a pas pu être dessiné.",
  es: "Resumen|Cambio|Motivación|Archivos|Otros cambios|Arquitectura|Componentes|Grupos de arquitectura|Contexto|Cambios y motivaciones|Detalles del componente|Qué cambió|Archivos fuente|Cerrar|Mostrar todo|Selecciona un componente en el plano para ver su función y sus cambios de código.|{count} detalle(s) del resumen, el plano o los contratos no coincidían con el diff y se omitieron. Regenera para intentarlo de nuevo.|Sin plano: no se pudo dibujar el diagrama del modelo.",
  it: "Riepilogo|Modifica|Motivazione|File|Altre modifiche|Architettura|Componenti|Gruppi architetturali|Contesto|Modifiche e motivazioni|Dettagli del componente|Cosa è cambiato|File sorgente|Chiudi|Mostra tutto|Seleziona un componente nello schema per vederne il ruolo e le modifiche al codice.|Dettagli del riepilogo, dello schema o dei contratti non corrispondenti al diff, omessi: {count}. Rigenera per riprovare.|Nessuno schema: non è stato possibile disegnare il diagramma del modello.",
  pt: "Resumo|Alteração|Motivação|Arquivos|Outras alterações|Arquitetura|Componentes|Grupos de arquitetura|Contexto|Alterações e motivações|Detalhes do componente|O que mudou|Arquivos de origem|Fechar|Mostrar tudo|Selecione um componente no diagrama para ver sua função e suas alterações de código.|Detalhes do resumo, do diagrama ou dos contratos sem correspondência no diff, omitidos: {count}. Gere novamente para tentar de novo.|Sem diagrama: não foi possível desenhar o diagrama do modelo.",
  nl: "Samenvatting|Wijziging|Motivatie|Bestanden|Overige wijzigingen|Architectuur|Componenten|Architectuurgroepen|Context|Wijzigingen en motivatie|Componentdetails|Wat er veranderde|Bronbestanden|Sluiten|Alles tonen|Selecteer een component in de blauwdruk om de rol en bronwijzigingen te bekijken.|{count} detail(s) van de samenvatting, blauwdruk of contracten kwam(en) niet overeen met de diff en zijn weggelaten. Genereer opnieuw om het nog eens te proberen.|Geen blauwdruk: het diagram van het model kon niet worden getekend.",
  pl: "Podsumowanie|Zmiana|Motywacja|Pliki|Inne zmiany|Architektura|Komponenty|Grupy architektury|Kontekst|Zmiany i motywacje|Szczegóły komponentu|Co się zmieniło|Pliki źródłowe|Zamknij|Pokaż wszystko|Wybierz komponent na schemacie, aby zobaczyć jego rolę i zmiany w kodzie.|Szczegóły podsumowania, schematu lub kontraktów niezgodne z diffem zostały pominięte ({count}). Wygeneruj ponownie, aby spróbować jeszcze raz.|Brak schematu: nie udało się narysować diagramu modelu.",
  uk: "Підсумок|Зміна|Мотивація|Файли|Інші зміни|Архітектура|Компоненти|Групи архітектури|Контекст|Зміни та мотивація|Деталі компонента|Що змінилося|Вихідні файли|Закрити|Показати все|Виберіть компонент на схемі, щоб побачити його роль і зміни в коді.|Деталі підсумку, схеми або контрактів, що не відповідали diff, пропущено ({count}). Згенеруйте ще раз, щоб спробувати знову.|Немає схеми: діаграму моделі не вдалося намалювати.",
  ru: "Итоги|Изменение|Мотивация|Файлы|Другие изменения|Архитектура|Компоненты|Группы архитектуры|Контекст|Изменения и мотивация|Детали компонента|Что изменилось|Исходные файлы|Закрыть|Показать все|Выберите компонент на схеме, чтобы увидеть его роль и изменения в коде.|Детали итогов, схемы или контрактов, не соответствующие diff, пропущены ({count}). Сгенерируйте заново, чтобы попробовать ещё раз.|Нет схемы: диаграмму модели не удалось нарисовать.",
  ja: "概要|変更|動機|ファイル|その他の変更|アーキテクチャ|コンポーネント|アーキテクチャグループ|コンテキスト|変更と動機|コンポーネントの詳細|変更内容|ソースファイル|閉じる|すべて表示|ブループリントでコンポーネントを選択すると、その役割とソースの変更を確認できます。|概要・ブループリント・コントラクトのうち差分と一致しない {count} 件の詳細を省略しました。再生成すると再試行できます。|ブループリントなし：モデルの図を描画できませんでした。",
  ko: "요약|변경|동기|파일|기타 변경|아키텍처|구성 요소|아키텍처 그룹|컨텍스트|변경 사항과 동기|구성 요소 세부 정보|변경 내용|소스 파일|닫기|모두 표시|청사진에서 구성 요소를 선택하면 역할과 소스 변경을 볼 수 있습니다.|요약, 청사진 또는 계약 중 diff와 맞지 않는 세부 정보 {count}개를 생략했습니다. 다시 생성하여 재시도하세요.|청사진 없음: 모델의 다이어그램을 그릴 수 없습니다.",
  zh: "概要|变更|动机|文件|其他变更|架构|组件|架构分组|上下文|变更与动机|组件详情|变更内容|源文件|关闭|全部显示|在蓝图中选择一个组件，查看其职责和源代码变更。|概要、蓝图或接口契约中有 {count} 项细节与差异不符，已省略。重新生成即可重试。|没有蓝图：无法绘制模型的图表。",
};

export const RECAP_TRANSLATIONS = Object.fromEntries(Object.entries(TABLE).map(([tag, row]) => {
  const values = row.split("|");
  if (values.length !== KEYS.length) throw new Error(`recap-language: ${tag} has ${values.length} strings, expected ${KEYS.length}`);
  return [tag, Object.fromEntries(KEYS.map((key, i) => [key, values[i]]))];
}));

/** The Recap's words for a report language (a tag, a locale or a language's name, like contractStrings). */
export function recapStrings(language = "en") {
  const contract = contractStrings(language);
  const tag = Object.keys(RECAP_TRANSLATIONS).find((t) => contractStrings(t) === contract) ?? "en";
  const words = RECAP_TRANSLATIONS[tag];
  return { ...words, tag, status: { added: contract.operations.added, modified: contract.operations.modified, context: words.context } };
}
