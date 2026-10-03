class Word {
  final String id;
  final String swedish;
  final String english;
  final String forms;

  /// Vocabulary level, for example:
  /// A1-A2
  /// B1-B2
  final String level;

  /// Primary chapter kept for backwards compatibility.
  final int chapter;

  /// All chapters in which this card occurs.
  ///
  /// This is important for the deduplicated B1-B2 database:
  /// one card may occur in more than one chapter.
  final List<int> chapters;

  final int? page;

  const Word({
    required this.id,
    required this.swedish,
    required this.english,
    this.forms = '',
    required this.level,
    required this.chapter,
    required this.chapters,
    this.page,
  });

  factory Word.fromJson(
    Map<String, dynamic> json, {
    String? defaultLevel,
  }) {
    final int chapter =
        (json['chapter'] as num?)?.toInt() ?? 0;

    final List<int> chapters = [];

    final rawChapters = json['chapters'];

    if (rawChapters is List) {
      for (final value in rawChapters) {
        if (value is num) {
          final parsedChapter = value.toInt();

          if (parsedChapter > 0 &&
              !chapters.contains(parsedChapter)) {
            chapters.add(parsedChapter);
          }
        }
      }
    }

    // Old A1-A2 database does not contain "chapters".
    // In that case we simply use its existing "chapter".
    if (chapters.isEmpty && chapter > 0) {
      chapters.add(chapter);
    }

    chapters.sort();

    return Word(
      id: json['id'] as String,
      swedish: json['swedish'] as String,
      english: json['english'] as String,
      forms: json['forms'] as String? ?? '',
      level:
          json['level'] as String? ??
          defaultLevel ??
          '',
      chapter: chapter,
      chapters: chapters,
      page: (json['page'] as num?)?.toInt(),
    );
  }

  bool belongsToChapter(int chapterNumber) {
    return chapters.contains(chapterNumber);
  }
}