class Word {
  final String id;
  final String swedish;
  final String english;
  final String forms;
  final int chapter;
  final int? page;

  const Word({
    required this.id,
    required this.swedish,
    required this.english,
    this.forms = '',
    required this.chapter,
    this.page,
  });

  factory Word.fromJson(Map<String, dynamic> json) {
    return Word(
      id: json['id'] as String,
      swedish: json['swedish'] as String,
      english: json['english'] as String,
      forms: json['forms'] as String? ?? '',
      chapter: json['chapter'] as int,
      page: json['page'] as int?,
    );
  }
}