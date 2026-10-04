class Word {
  final String id;
  final String swedish;
  final List<String> englishMeanings;
  final String level;
  final String pos;
  final String article;
  final List<String> ipa;
  final List<String> examples;
  final String translationSource;
  final String pronunciationSource;

  // SALDO-M noun morphology. Each field is a list because SALDO can
  // legitimately provide more than one accepted form.
  final List<String> nounIndefiniteSingular;
  final List<String> nounDefiniteSingular;
  final List<String> nounIndefinitePlural;
  final List<String> nounDefinitePlural;
  final String morphologySource;

  // SALDO-M verb morphology.
  final List<String> verbInfinitive;
  final List<String> verbPresent;
  final List<String> verbPreterite;
  final List<String> verbSupine;
  final String verbMorphologySource;

  const Word({
    required this.id,
    required this.swedish,
    required this.englishMeanings,
    required this.level,
    this.pos = '',
    this.article = '',
    this.ipa = const [],
    this.examples = const [],
    this.translationSource = '',
    this.pronunciationSource = '',
    this.nounIndefiniteSingular = const [],
    this.nounDefiniteSingular = const [],
    this.nounIndefinitePlural = const [],
    this.nounDefinitePlural = const [],
    this.morphologySource = '',
    this.verbInfinitive = const [],
    this.verbPresent = const [],
    this.verbPreterite = const [],
    this.verbSupine = const [],
    this.verbMorphologySource = '',
  });

  String get english => englishMeanings.join(', ');

  // Compatibility with old chapter screens. Kelly has no Rivstart chapters.
  int get chapter => 0;
  List<int> get chapters => const [];
  int? get page => null;
  bool belongsToChapter(int chapterNumber) => false;

  bool get hasNounForms =>
      nounDefiniteSingular.isNotEmpty ||
      nounIndefinitePlural.isNotEmpty ||
      nounDefinitePlural.isNotEmpty;

  String _joinVariants(List<String> values) => values.join('/');

  String get nounFormsLine {
    if (!hasNounForms) return '';
    final parts = <String>[];
    if (nounDefiniteSingular.isNotEmpty) {
      parts.add(_joinVariants(nounDefiniteSingular));
    }
    if (nounIndefinitePlural.isNotEmpty) {
      parts.add(_joinVariants(nounIndefinitePlural));
    }
    if (nounDefinitePlural.isNotEmpty) {
      parts.add(_joinVariants(nounDefinitePlural));
    }
    return parts.join(' • ');
  }

  // Clean presentation helpers used by the v2.4 flashcard layout.
  String get pronunciation =>
      ipa.isEmpty ? '' : '/${ipa.join(' / ')}/';

  // en / ett / att already carries the useful grammatical information.
  // For entries without such a marker, keep the POS as a fallback.
  String get verbFormsLine {
    final parts = <String>[];
    if (verbPresent.isNotEmpty) {
      parts.add(_joinVariants(verbPresent));
    }
    if (verbPreterite.isNotEmpty) {
      parts.add(_joinVariants(verbPreterite));
    }
    if (verbSupine.isNotEmpty) {
      parts.add(_joinVariants(verbSupine));
    }
    return parts.join(' • ');
  }

  String get morphologyLine =>
      nounFormsLine.isNotEmpty ? nounFormsLine : verbFormsLine;

  String get grammarLabel =>
      article.isNotEmpty ? article : pos;

  // Kept for compatibility with any older UI code.
  String get forms {
    final lines = <String>[];
    if (grammarLabel.isNotEmpty) {
      lines.add(grammarLabel);
    }
    if (morphologyLine.isNotEmpty) {
      lines.add(morphologyLine);
    }
    return lines.join('\n');
  }

  factory Word.fromJson(Map<String, dynamic> json) {
    List<String> stringList(dynamic value) {
      if (value is List) {
        return value
            .whereType<String>()
            .map((e) => e.trim())
            .where((e) => e.isNotEmpty)
            .toList();
      }
      if (value is String && value.trim().isNotEmpty) {
        return [value.trim()];
      }
      return const [];
    }

    final nounFormsRaw = json['noun_forms'];
    final nounForms = nounFormsRaw is Map
        ? Map<String, dynamic>.from(nounFormsRaw)
        : const <String, dynamic>{};

    final verbFormsRaw = json['verb_forms'];
    final verbForms = verbFormsRaw is Map
        ? Map<String, dynamic>.from(verbFormsRaw)
        : const <String, dynamic>{};

    return Word(
      id: json['id'] as String,
      swedish: json['swedish'] as String,
      englishMeanings: stringList(json['english']),
      level: json['cefr'] as String? ?? '',
      pos: json['pos'] as String? ?? '',
      article: json['article'] as String? ?? '',
      ipa: stringList(json['ipa']),
      examples: stringList(json['examples']),
      translationSource: json['translation_source'] as String? ?? '',
      pronunciationSource: json['pronunciation_source'] as String? ?? '',
      nounIndefiniteSingular:
          stringList(nounForms['indefinite_singular']),
      nounDefiniteSingular:
          stringList(nounForms['definite_singular']),
      nounIndefinitePlural:
          stringList(nounForms['indefinite_plural']),
      nounDefinitePlural:
          stringList(nounForms['definite_plural']),
      morphologySource: json['morphology_source'] as String? ?? '',
      verbInfinitive: stringList(verbForms['infinitive']),
      verbPresent: stringList(verbForms['present']),
      verbPreterite: stringList(verbForms['preterite']),
      verbSupine: stringList(verbForms['supine']),
      verbMorphologySource:
          json['verb_morphology_source'] as String? ?? '',
    );
  }
}
