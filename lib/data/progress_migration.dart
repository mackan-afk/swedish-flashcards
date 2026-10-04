import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

const String progressMigrationV1DoneKey =
    'progress_migration_rivstart_to_kelly_v1_done';

class _StoredProgress {
  final int level;
  final DateTime? nextReview;

  const _StoredProgress({
    required this.level,
    this.nextReview,
  });
}

_StoredProgress? _decodeProgress(String? raw) {
  if (raw == null) return null;
  try {
    final data = jsonDecode(raw);
    if (data is! Map) return null;
    final level = data['level'];
    if (level is! num) return null;
    final rawDate = data['nextReview'];
    return _StoredProgress(
      level: level.toInt(),
      nextReview: rawDate is String ? DateTime.tryParse(rawDate) : null,
    );
  } catch (_) {
    return null;
  }
}

_StoredProgress? _readOldProgress(
  SharedPreferences prefs,
  String oldId,
) {
  final modern = _decodeProgress(prefs.getString('progress_$oldId'));
  if (modern != null) return modern;

  final legacy = prefs.getString('status_$oldId');
  if (legacy == 'learning') {
    return const _StoredProgress(level: 1);
  }
  if (legacy == 'known') {
    final now = DateTime.now();
    final tomorrow = DateTime(
      now.year,
      now.month,
      now.day,
    ).add(const Duration(days: 1));
    return _StoredProgress(level: 2, nextReview: tomorrow);
  }
  return null;
}

_StoredProgress _merge(
  _StoredProgress a,
  _StoredProgress b,
) {
  if (a.level > b.level) return a;
  if (b.level > a.level) return b;

  if (a.nextReview == null) return b.nextReview == null ? a : b;
  if (b.nextReview == null) return a;

  // For equal SRS level keep the later review date so migration never
  // makes a learned card due earlier than it was before.
  return b.nextReview!.isAfter(a.nextReview!) ? b : a;
}

Future<void> migrateRivstartProgressToKellyV1() async {
  final prefs = await SharedPreferences.getInstance();

  if (prefs.getBool(progressMigrationV1DoneKey) == true) {
    return;
  }

  final raw = await rootBundle.loadString(
    'assets/progress_migration_v1.json',
  );
  final decoded = jsonDecode(raw);

  if (decoded is! Map || decoded['old_to_kelly'] is! Map) {
    throw const FormatException('Invalid progress migration map.');
  }

  final map = Map<String, dynamic>.from(decoded['old_to_kelly'] as Map);
  final mergedByKelly = <String, _StoredProgress>{};

  for (final entry in map.entries) {
    final oldProgress = _readOldProgress(prefs, entry.key);
    if (oldProgress == null || oldProgress.level <= 0) continue;

    final kellyId = entry.value.toString();
    final current = mergedByKelly[kellyId];
    mergedByKelly[kellyId] =
        current == null ? oldProgress : _merge(current, oldProgress);
  }

  for (final entry in mergedByKelly.entries) {
    final key = 'progress_${entry.key}';
    final existing = _decodeProgress(prefs.getString(key));
    final finalProgress =
        existing == null ? entry.value : _merge(existing, entry.value);

    await prefs.setString(
      key,
      jsonEncode({
        'level': finalProgress.level,
        'nextReview': finalProgress.nextReview?.toIso8601String(),
      }),
    );
  }

  // Old progress_/status_ keys are deliberately preserved.
  await prefs.setBool(progressMigrationV1DoneKey, true);
}
