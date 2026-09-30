class WordProgress {
  final int level;
  final DateTime? nextReview;

  const WordProgress({
    required this.level,
    this.nextReview,
  });

  bool get isDue {
    if (nextReview == null) {
      return true;
    }

    return !nextReview!.isAfter(DateTime.now());
  }

  bool get isNew {
    return level == 0;
  }

  bool get isLearning {
    return level == 1;
  }

  bool get isReview {
    return level >= 2;
  }

  WordProgress copyWith({
    int? level,
    DateTime? nextReview,
  }) {
    return WordProgress(
      level: level ?? this.level,
      nextReview: nextReview ?? this.nextReview,
    );
  }
}