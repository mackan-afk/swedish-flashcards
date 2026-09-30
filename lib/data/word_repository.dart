import 'dart:convert';

import 'package:flutter/services.dart';

import '../models/word.dart';

class WordRepository {
  static Future<List<Word>> loadWords() async {
    final String jsonString =
        await rootBundle.loadString('assets/words.json');

    final List<dynamic> jsonData = json.decode(jsonString);

    return jsonData
        .map(
          (item) => Word.fromJson(
            item as Map<String, dynamic>,
          ),
        )
        .toList();
  }
}