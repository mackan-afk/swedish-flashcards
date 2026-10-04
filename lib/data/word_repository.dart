import 'dart:convert';

import 'package:flutter/services.dart';

import '../models/word.dart';

class WordRepository {
  static const String vocabularyAsset = 'assets/words_v2.json';

  static Future<List<Word>> loadWords() async {
    final jsonString = await rootBundle.loadString(vocabularyAsset);
    final decoded = json.decode(jsonString);

    if (decoded is! List) {
      throw const FormatException(
        'Vocabulary file must contain a JSON list.',
      );
    }

    final words = decoded.map<Word>((item) {
      if (item is! Map) {
        throw const FormatException(
          'Invalid vocabulary record.',
        );
      }
      return Word.fromJson(Map<String, dynamic>.from(item));
    }).toList();

    _validate(words);
    return words;
  }

  static void _validate(List<Word> words) {
    final ids = <String>{};
    const allowedLevels = {'A1', 'A2', 'B1', 'B2', 'C1', 'C2'};

    for (final word in words) {
      if (!ids.add(word.id)) {
        throw FormatException('Duplicate word ID: ${word.id}');
      }
      if (word.swedish.trim().isEmpty ||
          word.englishMeanings.isEmpty ||
          !allowedLevels.contains(word.level)) {
        throw FormatException('Invalid vocabulary record: ${word.id}');
      }
    }
  }
}
