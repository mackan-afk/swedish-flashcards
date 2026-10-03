import 'dart:convert';

import 'package:flutter/services.dart';

import '../models/word.dart';

class WordRepository {
  static const String a1a2Asset =
      'assets/words.json';

  static const String b1b2Asset =
      'assets/b1b2_words.json';

  /// Loads the complete vocabulary collection used by the app.
  ///
  /// Existing A1-A2 IDs are left completely untouched,
  /// so existing SRS progress remains compatible.
  static Future<List<Word>> loadWords() async {
    final results = await Future.wait([
      loadA1A2Words(),
      loadB1B2Words(),
    ]);

    final words = <Word>[
      ...results[0],
      ...results[1],
    ];

    _validateUniqueIds(words);

    return words;
  }

  static Future<List<Word>>
      loadA1A2Words() async {
    return _loadAsset(
      a1a2Asset,
      defaultLevel: 'A1-A2',
    );
  }

  static Future<List<Word>>
      loadB1B2Words() async {
    return _loadAsset(
      b1b2Asset,
      defaultLevel: 'B1-B2',
    );
  }

  static Future<List<Word>> _loadAsset(
    String assetPath, {
    required String defaultLevel,
  }) async {
    final String jsonString =
        await rootBundle.loadString(assetPath);

    final dynamic decoded =
        json.decode(jsonString);

    if (decoded is! List) {
      throw FormatException(
        'Vocabulary file must contain a JSON list: '
        '$assetPath',
      );
    }

    return decoded.map<Word>((item) {
      if (item is! Map) {
        throw FormatException(
          'Invalid vocabulary record in '
          '$assetPath',
        );
      }

      return Word.fromJson(
        Map<String, dynamic>.from(item),
        defaultLevel: defaultLevel,
      );
    }).toList();
  }

  static void _validateUniqueIds(
    List<Word> words,
  ) {
    final ids = <String>{};

    for (final word in words) {
      if (!ids.add(word.id)) {
        throw FormatException(
          'Duplicate word ID found: '
          '${word.id}',
        );
      }
    }
  }
}