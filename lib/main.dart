import 'dart:convert';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'data/word_repository.dart';
import 'models/word.dart';
import 'models/word_progress.dart';

void main() {
  runApp(const SwedishFlashcardsApp());
}

// ============================================================
// APP
// ============================================================

class SwedishFlashcardsApp extends StatelessWidget {
  const SwedishFlashcardsApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Swedish Flashcards',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF006AA7),
          brightness: Brightness.light,
        ),
        scaffoldBackgroundColor: const Color(0xFFF7F9FC),
        useMaterial3: true,
        cardTheme: const CardThemeData(
          color: Colors.white,
          surfaceTintColor: Colors.transparent,
          margin: EdgeInsets.zero,
        ),
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(0xFFF7F9FC),
          surfaceTintColor: Colors.transparent,
          centerTitle: true,
        ),
      ),
      home: const HomePage(),
    );
  }
}

// ============================================================
// SPACED REPETITION
// ============================================================

// Level:
// 0 = New
// 1 = Learning
// 2 = 1 day
// 3 = 3 days
// 4 = 7 days
// 5 = 14 days
// 6 = 30 days

const Map<int, int> reviewIntervals = {
  2: 1,
  3: 3,
  4: 7,
  5: 14,
  6: 30,
};

DateTime startOfDay(DateTime date) {
  return DateTime(
    date.year,
    date.month,
    date.day,
  );
}

bool isProgressDue(WordProgress progress) {
  if (progress.level < 2) {
    return false;
  }

  if (progress.nextReview == null) {
    return true;
  }

  final today = startOfDay(DateTime.now());
  final reviewDay = startOfDay(progress.nextReview!);

  return !reviewDay.isAfter(today);
}

// ============================================================
// STORAGE
// ============================================================

String progressKey(String wordId) {
  return 'progress_$wordId';
}

String oldStatusKey(String wordId) {
  return 'status_$wordId';
}

Future<Map<String, WordProgress>> loadProgress(
  List<Word> words,
) async {
  final prefs = await SharedPreferences.getInstance();

  final Map<String, WordProgress> result = {};

  for (final word in words) {
    final saved = prefs.getString(
      progressKey(word.id),
    );

    // --------------------------------------------------------
    // NEW FORMAT
    // --------------------------------------------------------

    if (saved != null) {
      try {
        final Map<String, dynamic> data =
            jsonDecode(saved);

        final level = data['level'] as int? ?? 0;

        final nextReviewString =
            data['nextReview'] as String?;

        DateTime? nextReview;

        if (nextReviewString != null) {
          nextReview =
              DateTime.tryParse(nextReviewString);
        }

        if (level > 0) {
          result[word.id] = WordProgress(
            level: level,
            nextReview: nextReview,
          );
        }

        continue;
      } catch (_) {
        // If stored data is corrupted,
        // try the old format below.
      }
    }

    // --------------------------------------------------------
    // MIGRATE OLD FORMAT
    // --------------------------------------------------------

    final oldStatus = prefs.getString(
      oldStatusKey(word.id),
    );

    if (oldStatus == 'learning') {
      const migratedProgress = WordProgress(
        level: 1,
      );

      result[word.id] = migratedProgress;

      await saveProgress(
        word,
        migratedProgress,
      );
    } else if (oldStatus == 'known') {
      final tomorrow = startOfDay(
        DateTime.now().add(
          const Duration(days: 1),
        ),
      );

      final migratedProgress = WordProgress(
        level: 2,
        nextReview: tomorrow,
      );

      result[word.id] = migratedProgress;

      await saveProgress(
        word,
        migratedProgress,
      );
    }
  }

  return result;
}

Future<void> saveProgress(
  Word word,
  WordProgress progress,
) async {
  final prefs = await SharedPreferences.getInstance();

  final data = {
    'level': progress.level,
    'nextReview':
        progress.nextReview?.toIso8601String(),
  };

  await prefs.setString(
    progressKey(word.id),
    jsonEncode(data),
  );
}

Future<void> resetAllProgress() async {
  final prefs = await SharedPreferences.getInstance();

  final keys = prefs.getKeys().toList();

  for (final key in keys) {
    if (key.startsWith('progress_') ||
        key.startsWith('status_')) {
      await prefs.remove(key);
    }
  }


  await resetStatistics();
}

// ============================================================
// STUDY STATISTICS
// ============================================================

String statisticsDateKey(DateTime date) {
  final day = startOfDay(date);
  final year = day.year.toString().padLeft(4, '0');
  final month = day.month.toString().padLeft(2, '0');
  final dayNumber = day.day.toString().padLeft(2, '0');
  return '$year-$month-$dayNumber';
}

Future<void> recordStudyAnswer({
  required bool known,
}) async {
  final prefs = await SharedPreferences.getInstance();

  final totalAnswers = prefs.getInt('stats_total_answers') ?? 0;
  final totalKnown = prefs.getInt('stats_total_known') ?? 0;
  final totalLearning = prefs.getInt('stats_total_learning') ?? 0;

  await prefs.setInt('stats_total_answers', totalAnswers + 1);

  if (known) {
    await prefs.setInt('stats_total_known', totalKnown + 1);
  } else {
    await prefs.setInt('stats_total_learning', totalLearning + 1);
  }

  final rawDays = prefs.getString('stats_days');
  Map<String, dynamic> days = {};

  if (rawDays != null) {
    try {
      days = Map<String, dynamic>.from(jsonDecode(rawDays));
    } catch (_) {
      days = {};
    }
  }

  final todayKey = statisticsDateKey(DateTime.now());
  final existing = days[todayKey];
  final today = existing is Map
      ? Map<String, dynamic>.from(existing)
      : <String, dynamic>{};

  today['studied'] = (today['studied'] as int? ?? 0) + 1;
  today['known'] = (today['known'] as int? ?? 0) + (known ? 1 : 0);
  today['learning'] =
      (today['learning'] as int? ?? 0) + (known ? 0 : 1);

  days[todayKey] = today;
  await prefs.setString('stats_days', jsonEncode(days));
}

Future<void> resetStatistics() async {
  final prefs = await SharedPreferences.getInstance();
  await prefs.remove('stats_total_answers');
  await prefs.remove('stats_total_known');
  await prefs.remove('stats_total_learning');
  await prefs.remove('stats_days');
}

class StudyStatistics {
  final int todayStudied;
  final int todayKnown;
  final int todayLearning;
  final int totalAnswers;
  final int totalKnown;
  final int totalLearning;
  final int currentStreak;

  const StudyStatistics({
    required this.todayStudied,
    required this.todayKnown,
    required this.todayLearning,
    required this.totalAnswers,
    required this.totalKnown,
    required this.totalLearning,
    required this.currentStreak,
  });
}

Future<StudyStatistics> loadStatistics() async {
  final prefs = await SharedPreferences.getInstance();

  final totalAnswers = prefs.getInt('stats_total_answers') ?? 0;
  final totalKnown = prefs.getInt('stats_total_known') ?? 0;
  final totalLearning = prefs.getInt('stats_total_learning') ?? 0;

  Map<String, dynamic> days = {};
  final rawDays = prefs.getString('stats_days');

  if (rawDays != null) {
    try {
      days = Map<String, dynamic>.from(jsonDecode(rawDays));
    } catch (_) {
      days = {};
    }
  }

  final today = startOfDay(DateTime.now());
  final todayDataRaw = days[statisticsDateKey(today)];
  final todayData = todayDataRaw is Map
      ? Map<String, dynamic>.from(todayDataRaw)
      : <String, dynamic>{};

  int streak = 0;
  DateTime cursor = today;

  // A streak remains active during a day before the user has studied,
  // as long as they studied yesterday. Once today's first answer is
  // recorded, today becomes part of the streak.
  if (!days.containsKey(statisticsDateKey(cursor))) {
    cursor = cursor.subtract(const Duration(days: 1));
  }

  while (true) {
    final dataRaw = days[statisticsDateKey(cursor)];
    if (dataRaw is! Map) break;

    final data = Map<String, dynamic>.from(dataRaw);
    final studied = data['studied'] as int? ?? 0;
    if (studied <= 0) break;

    streak++;
    cursor = cursor.subtract(const Duration(days: 1));
  }

  return StudyStatistics(
    todayStudied: todayData['studied'] as int? ?? 0,
    todayKnown: todayData['known'] as int? ?? 0,
    todayLearning: todayData['learning'] as int? ?? 0,
    totalAnswers: totalAnswers,
    totalKnown: totalKnown,
    totalLearning: totalLearning,
    currentStreak: streak,
  );
}

// ============================================================
// ANSWER LOGIC
// ============================================================

Future<WordProgress> markLearning(
  Word word,
) async {
  const progress = WordProgress(
    level: 1,
    nextReview: null,
  );

  await saveProgress(
    word,
    progress,
  );

  return progress;
}

Future<WordProgress> markKnown(
  Word word,
  WordProgress? currentProgress,
) async {
  final currentLevel =
      currentProgress?.level ?? 0;

  int nextLevel;

  if (currentLevel <= 1) {
    nextLevel = 2;
  } else {
    nextLevel = min(
      currentLevel + 1,
      6,
    );
  }

  final days = reviewIntervals[nextLevel] ?? 30;

  final nextReview = startOfDay(
    DateTime.now().add(
      Duration(days: days),
    ),
  );

  final progress = WordProgress(
    level: nextLevel,
    nextReview: nextReview,
  );

  await saveProgress(
    word,
    progress,
  );

  return progress;
}

// ============================================================
// SESSION BUILDERS
// ============================================================

List<Word> buildStudySession({
  required List<Word> sourceWords,
  required Map<String, WordProgress> progress,
  required int? sessionSize,
}) {
  final random = Random();

  final dueWords = <Word>[];
  final learningWords = <Word>[];
  final newWords = <Word>[];

  for (final word in sourceWords) {
    final wordProgress = progress[word.id];

    if (wordProgress == null ||
        wordProgress.level == 0) {
      newWords.add(word);
      continue;
    }

    if (wordProgress.level == 1) {
      learningWords.add(word);
      continue;
    }

    if (isProgressDue(wordProgress)) {
      dueWords.add(word);
    }
  }

  dueWords.shuffle(random);
  learningWords.shuffle(random);
  newWords.shuffle(random);

  final candidates = [
    ...dueWords,
    ...learningWords,
    ...newWords,
  ];

  if (sessionSize == null) {
    return candidates;
  }

  return candidates.take(sessionSize).toList();
}

List<Word> buildDailyReviewSession({
  required List<Word> sourceWords,
  required Map<String, WordProgress> progress,
}) {
  final random = Random();

  final dueWords = sourceWords.where((word) {
    final wordProgress = progress[word.id];

    return wordProgress != null &&
        wordProgress.level >= 2 &&
        isProgressDue(wordProgress);
  }).toList();

  dueWords.shuffle(random);

  return dueWords;
}

// ============================================================
// HOME PAGE
// ============================================================

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() =>
      _HomePageState();
}

class _HomePageState extends State<HomePage> {
  List<Word> allWords = [];

  Map<String, WordProgress> progress = {};

  bool isLoading = true;

  String? errorMessage;

  @override
  void initState() {
    super.initState();
    loadAppData();
  }

  // ----------------------------------------------------------
  // LOAD
  // ----------------------------------------------------------

  Future<void> loadAppData() async {
    try {
      final words =
          await WordRepository.loadWords();

      final loadedProgress =
          await loadProgress(words);

      if (!mounted) return;

      setState(() {
        allWords = words;
        progress = loadedProgress;
        isLoading = false;
        errorMessage = null;
      });
    } catch (error) {
      if (!mounted) return;

      setState(() {
        isLoading = false;
        errorMessage = error.toString();
      });
    }
  }

  Future<void> refreshProgress() async {
    final loadedProgress =
        await loadProgress(allWords);

    if (!mounted) return;

    setState(() {
      progress = loadedProgress;
    });
  }

  // ----------------------------------------------------------
  // COUNTERS
  // ----------------------------------------------------------

  int get newCount {
    return allWords.where((word) {
      final p = progress[word.id];

      return p == null || p.level == 0;
    }).length;
  }

  int get learningCount {
    return allWords.where((word) {
      return progress[word.id]?.level == 1;
    }).length;
  }

  int get dueCount {
    return allWords.where((word) {
      final p = progress[word.id];

      return p != null &&
          p.level >= 2 &&
          isProgressDue(p);
    }).length;
  }

  int get learnedCount {
    return allWords.where((word) {
      final p = progress[word.id];

      return p != null && p.level >= 2;
    }).length;
  }

  // ----------------------------------------------------------
  // NAVIGATION
  // ----------------------------------------------------------

  Future<void> openStudyOptions({
    required String title,
    required List<Word> words,
  }) async {
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) =>
            StudyOptionsPage(
          title: title,
          words: words,
          progress: progress,
        ),
      ),
    );

    await refreshProgress();
  }

  Future<void> openChapterSelection() async {
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) =>
            ChapterSelectionPage(
          allWords: allWords,
          progress: progress,
        ),
      ),
    );

    await refreshProgress();
  }

  Future<void> openStatistics() async {
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => StatisticsPage(
          allWords: allWords,
          progress: progress,
        ),
      ),
    );

    await refreshProgress();
  }

  Future<void> openSettings() async {
    final wasReset = await Navigator.push<bool>(
      context,
      MaterialPageRoute(
        builder: (context) =>
            const SettingsPage(),
      ),
    );

    if (wasReset == true) {
      await refreshProgress();
    }
  }

  // ----------------------------------------------------------
  // DAILY REVIEW
  // ----------------------------------------------------------

  Future<void> startDailyReview() async {
    final reviewWords =
        buildDailyReviewSession(
      sourceWords: allWords,
      progress: progress,
    );

    if (reviewWords.isEmpty) {
      if (!mounted) return;

      ScaffoldMessenger.of(context)
          .showSnackBar(
        const SnackBar(
          content: Text(
            'No reviews are due right now.',
          ),
        ),
      );

      return;
    }

    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) =>
            FlashcardPage(
          words: reviewWords,
          title: 'Daily Review',
          progress: progress,
        ),
      ),
    );

    await refreshProgress();
  }

  // ----------------------------------------------------------
  // BUILD
  // ----------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    if (isLoading) {
      return const Scaffold(
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              CircularProgressIndicator(),
              SizedBox(height: 20),
              Text(
                'Loading vocabulary...',
                style: TextStyle(fontSize: 18),
              ),
            ],
          ),
        ),
      );
    }

    if (errorMessage != null) {
      return Scaffold(
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(30),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(
                  Icons.error_outline,
                  size: 60,
                  color: Colors.red,
                ),
                const SizedBox(height: 20),
                const Text(
                  'Could not load vocabulary',
                  style: TextStyle(
                    fontSize: 24,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 12),
                Text(
                  errorMessage!,
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 25),
                FilledButton(
                  onPressed: () {
                    setState(() {
                      isLoading = true;
                      errorMessage = null;
                    });
                    loadAppData();
                  },
                  child: const Text('TRY AGAIN'),
                ),
              ],
            ),
          ),
        ),
      );
    }

    final completion = allWords.isEmpty
        ? 0.0
        : learnedCount / allWords.length;

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(
              20,
              18,
              20,
              28,
            ),
            child: ConstrainedBox(
              constraints: const BoxConstraints(
                maxWidth: 550,
              ),
              child: Column(
                crossAxisAlignment:
                    CrossAxisAlignment.stretch,
                children: [
                  // HEADER
                  Row(
                    children: [
                      Container(
                        width: 54,
                        height: 54,
                        decoration: BoxDecoration(
                          color: const Color(0xFF006AA7),
                          borderRadius:
                              BorderRadius.circular(16),
                        ),
                        alignment: Alignment.center,
                        child: const Text(
                          '🇸🇪',
                          style: TextStyle(fontSize: 30),
                        ),
                      ),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Column(
                          crossAxisAlignment:
                              CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'Swedish Flashcards',
                              style: TextStyle(
                                fontSize: 25,
                                fontWeight: FontWeight.w800,
                                letterSpacing: -0.5,
                              ),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              '${allWords.length} words in your collection',
                              style: TextStyle(
                                color: Colors.grey.shade600,
                                fontSize: 14,
                              ),
                            ),
                          ],
                        ),
                      ),
                      IconButton(
                        tooltip: 'Statistics',
                        onPressed: openStatistics,
                        icon: const Icon(
                          Icons.bar_chart_rounded,
                        ),
                      ),
                      IconButton(
                        tooltip: 'Settings',
                        onPressed: openSettings,
                        icon: const Icon(
                          Icons.settings_outlined,
                        ),
                      ),
                    ],
                  ),

                  const SizedBox(height: 28),

                  const SectionTitle(
                    title: 'YOUR PROGRESS',
                  ),
                  const SizedBox(height: 12),

                  Row(
                    children: [
                      Expanded(
                        child: ProgressStatCard(
                          icon: Icons.fiber_new_outlined,
                          title: 'New',
                          count: newCount,
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: ProgressStatCard(
                          icon: Icons.school_outlined,
                          title: 'Learning',
                          count: learningCount,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      Expanded(
                        child: ProgressStatCard(
                          icon: Icons.schedule_outlined,
                          title: 'Due',
                          count: dueCount,
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: ProgressStatCard(
                          icon: Icons.check_circle_outline,
                          title: 'Learned',
                          count: learnedCount,
                        ),
                      ),
                    ],
                  ),

                  const SizedBox(height: 18),

                  ClipRRect(
                    borderRadius: BorderRadius.circular(20),
                    child: LinearProgressIndicator(
                      value: completion,
                      minHeight: 8,
                      backgroundColor:
                          const Color(0xFFDCEAF5),
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '$learnedCount of ${allWords.length} words entered the review system',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Colors.grey.shade600,
                      fontSize: 13,
                    ),
                  ),

                  const SizedBox(height: 30),

                  const SectionTitle(title: 'TODAY'),
                  const SizedBox(height: 12),

                  if (dueCount > 0)
                    DailyReviewTile(
                      dueCount: dueCount,
                      onTap: startDailyReview,
                    )
                  else
                    const DailyCompleteTile(),

                  const SizedBox(height: 30),

                  const SectionTitle(
                    title: 'CHOOSE MATERIAL',
                  ),
                  const SizedBox(height: 12),

                  MaterialTile(
                    icon: Icons.library_books_outlined,
                    title: 'All Words',
                    subtitle:
                        'Entire vocabulary collection',
                    onTap: () {
                      openStudyOptions(
                        title: 'All Words',
                        words: allWords,
                      );
                    },
                  ),

                  const SizedBox(height: 10),

                  MaterialTile(
                    icon: Icons.menu_book_outlined,
                    title: 'By Chapter',
                    subtitle: 'Choose Kapitel 1–20',
                    onTap: openChapterSelection,
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// ============================================================
// STATISTICS
// ============================================================

class StatisticsPage extends StatefulWidget {
  final List<Word> allWords;
  final Map<String, WordProgress> progress;

  const StatisticsPage({
    super.key,
    required this.allWords,
    required this.progress,
  });

  @override
  State<StatisticsPage> createState() => _StatisticsPageState();
}

class _StatisticsPageState extends State<StatisticsPage> {
  StudyStatistics? statistics;
  bool isLoading = true;

  @override
  void initState() {
    super.initState();
    loadData();
  }

  Future<void> loadData() async {
    final loaded = await loadStatistics();
    if (!mounted) return;

    setState(() {
      statistics = loaded;
      isLoading = false;
    });
  }

  int get newCount => widget.allWords.where((word) {
        final p = widget.progress[word.id];
        return p == null || p.level == 0;
      }).length;

  int get learningCount => widget.allWords.where((word) {
        return widget.progress[word.id]?.level == 1;
      }).length;

  int get learnedCount => widget.allWords.where((word) {
        final p = widget.progress[word.id];
        return p != null && p.level >= 2;
      }).length;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Statistics'),
      ),
      body: SafeArea(
        child: isLoading
            ? const Center(child: CircularProgressIndicator())
            : Center(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.all(24),
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 550),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const Icon(
                          Icons.bar_chart_rounded,
                          size: 65,
                          color: Color(0xFF006AA7),
                        ),
                        const SizedBox(height: 12),
                        const Text(
                          'Your Statistics',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontSize: 30,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          statistics!.currentStreak == 1
                              ? '🔥 1 day streak'
                              : '🔥 ${statistics!.currentStreak} day streak',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            color: Colors.grey.shade600,
                            fontSize: 15,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(height: 34),
                        const SectionTitle(title: 'TODAY'),
                        const SizedBox(height: 12),
                        Row(
                          children: [
                            Expanded(
                              child: StatisticsCard(
                                icon: Icons.style_outlined,
                                value: statistics!.todayStudied,
                                label: 'Studied',
                              ),
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: StatisticsCard(
                                icon: Icons.check_rounded,
                                value: statistics!.todayKnown,
                                label: 'I Know',
                              ),
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: StatisticsCard(
                                icon: Icons.school_outlined,
                                value: statistics!.todayLearning,
                                label: 'Learning',
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 30),
                        const SectionTitle(title: 'OVERALL PROGRESS'),
                        const SizedBox(height: 12),
                        Row(
                          children: [
                            Expanded(
                              child: StatisticsCard(
                                icon: Icons.check_circle_outline,
                                value: learnedCount,
                                label: 'Learned',
                              ),
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: StatisticsCard(
                                icon: Icons.school_outlined,
                                value: learningCount,
                                label: 'Learning',
                              ),
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: StatisticsCard(
                                icon: Icons.fiber_new_outlined,
                                value: newCount,
                                label: 'New',
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 30),
                        const SectionTitle(title: 'ALL TIME'),
                        const SizedBox(height: 12),
                        Card(
                          elevation: 0,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(18),
                            side: BorderSide(color: Colors.grey.shade200),
                          ),
                          child: Padding(
                            padding: const EdgeInsets.all(20),
                            child: Column(
                              children: [
                                StatisticsRow(
                                  label: 'Total answers',
                                  value: statistics!.totalAnswers,
                                ),
                                const Divider(height: 28),
                                StatisticsRow(
                                  label: 'I Know answers',
                                  value: statistics!.totalKnown,
                                ),
                                const Divider(height: 28),
                                StatisticsRow(
                                  label: 'Learning answers',
                                  value: statistics!.totalLearning,
                                ),
                              ],
                            ),
                          ),
                        ),
                        const SizedBox(height: 18),
                        Text(
                          'Statistics are counted from this version of the app onward.',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            color: Colors.grey.shade600,
                            fontSize: 13,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
      ),
    );
  }
}

// ============================================================
// SETTINGS
// ============================================================

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});

  @override
  State<SettingsPage> createState() =>
      _SettingsPageState();
}

class _SettingsPageState
    extends State<SettingsPage> {
  bool isResetting = false;

  Future<void> confirmReset() async {
    final firstConfirmation =
        await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text(
            'Reset all progress?',
          ),
          content: const Text(
            'This will remove all learning progress, '
            'review levels and scheduled reviews.\n\n'
            'Your vocabulary database will not be deleted.',
          ),
          actions: [
            TextButton(
              onPressed: () {
                Navigator.pop(
                  dialogContext,
                  false,
                );
              },
              child: const Text('CANCEL'),
            ),
            FilledButton(
              onPressed: () {
                Navigator.pop(
                  dialogContext,
                  true,
                );
              },
              child: const Text('CONTINUE'),
            ),
          ],
        );
      },
    );

    if (firstConfirmation != true ||
        !mounted) {
      return;
    }

    final finalConfirmation =
        await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          icon: const Icon(
            Icons.warning_amber_rounded,
            size: 45,
          ),
          title: const Text(
            'Are you absolutely sure?',
          ),
          content: const Text(
            'This action cannot be undone. '
            'All words will return to New.',
          ),
          actions: [
            TextButton(
              onPressed: () {
                Navigator.pop(
                  dialogContext,
                  false,
                );
              },
              child: const Text('CANCEL'),
            ),
            FilledButton(
              onPressed: () {
                Navigator.pop(
                  dialogContext,
                  true,
                );
              },
              child:
                  const Text('RESET'),
            ),
          ],
        );
      },
    );

    if (finalConfirmation != true ||
        !mounted) {
      return;
    }

    setState(() {
      isResetting = true;
    });

    await resetAllProgress();

    if (!mounted) return;

    setState(() {
      isResetting = false;
    });

    ScaffoldMessenger.of(context)
        .showSnackBar(
      const SnackBar(
        content: Text(
          'Learning progress has been reset.',
        ),
      ),
    );

    Navigator.pop(context, true);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Settings'),
      ),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding:
                const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints:
                  const BoxConstraints(
                maxWidth: 550,
              ),
              child: Column(
                crossAxisAlignment:
                    CrossAxisAlignment.stretch,
                children: [
                  const Icon(
                    Icons.settings_outlined,
                    size: 65,
                  ),

                  const SizedBox(height: 15),

                  const Text(
                    'Settings',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 30,
                      fontWeight:
                          FontWeight.bold,
                    ),
                  ),

                  const SizedBox(height: 40),

                  const SectionTitle(
                    title: 'LEARNING DATA',
                  ),

                  const SizedBox(height: 12),

                  Card(
                    child: Padding(
                      padding:
                          const EdgeInsets.all(
                        20,
                      ),
                      child: Column(
                        crossAxisAlignment:
                            CrossAxisAlignment
                                .start,
                        children: [
                          const Row(
                            children: [
                              Icon(
                                Icons
                                    .restart_alt,
                                size: 30,
                              ),
                              SizedBox(width: 12),
                              Expanded(
                                child: Text(
                                  'Reset Progress',
                                  style:
                                      TextStyle(
                                    fontSize: 18,
                                    fontWeight:
                                        FontWeight
                                            .bold,
                                  ),
                                ),
                              ),
                            ],
                          ),

                          const SizedBox(
                            height: 12,
                          ),

                          const Text(
                            'Return all flashcards to New '
                            'and remove all scheduled reviews.',
                            style: TextStyle(
                              color: Colors.grey,
                            ),
                          ),

                          const SizedBox(
                            height: 20,
                          ),

                          SizedBox(
                            width:
                                double.infinity,
                            child:
                                OutlinedButton
                                    .icon(
                              onPressed:
                                  isResetting
                                      ? null
                                      : confirmReset,
                              icon: isResetting
                                  ? const SizedBox(
                                      width: 18,
                                      height: 18,
                                      child:
                                          CircularProgressIndicator(
                                        strokeWidth:
                                            2,
                                      ),
                                    )
                                  : const Icon(
                                      Icons
                                          .delete_outline,
                                    ),
                              label: Text(
                                isResetting
                                    ? 'RESETTING...'
                                    : 'RESET ALL PROGRESS',
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),

                  const SizedBox(height: 25),

                  const Text(
                    'Resetting progress does not modify '
                    'the vocabulary database.',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Colors.grey,
                      fontSize: 13,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// ============================================================
// CHAPTER SELECTION
// ============================================================

class ChapterSelectionPage
    extends StatefulWidget {
  final List<Word> allWords;
  final Map<String, WordProgress> progress;

  const ChapterSelectionPage({
    super.key,
    required this.allWords,
    required this.progress,
  });

  @override
  State<ChapterSelectionPage> createState() =>
      _ChapterSelectionPageState();
}

class _ChapterSelectionPageState
    extends State<ChapterSelectionPage> {
  late Map<String, WordProgress> progress;

  @override
  void initState() {
    super.initState();

    progress =
        Map<String, WordProgress>.from(
      widget.progress,
    );
  }

  Future<void> refreshProgress() async {
    final loaded =
        await loadProgress(widget.allWords);

    if (!mounted) return;

    setState(() {
      progress = loaded;
    });
  }

  Future<void> openChapter(
    int chapter,
    List<Word> words,
  ) async {
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) =>
            StudyOptionsPage(
          title: 'Kapitel $chapter',
          words: words,
          progress: progress,
        ),
      ),
    );

    await refreshProgress();
  }

  @override
  Widget build(BuildContext context) {
    final chapters = widget.allWords
        .map((word) => word.chapter)
        .where((chapter) => chapter > 0)
        .toSet()
        .toList()
      ..sort();

    return Scaffold(
      appBar: AppBar(
        title: const Text('By Chapter'),
      ),
      body: SafeArea(
        child: Center(
          child: ListView(
            padding:
                const EdgeInsets.all(24),
            children: [
              Center(
                child: ConstrainedBox(
                  constraints:
                      const BoxConstraints(
                    maxWidth: 550,
                  ),
                  child: Column(
                    children: [
                      const Icon(
                        Icons
                            .menu_book_outlined,
                        size: 60,
                      ),
                      const SizedBox(
                        height: 15,
                      ),
                      const Text(
                        'Choose a chapter',
                        style: TextStyle(
                          fontSize: 28,
                          fontWeight:
                              FontWeight.bold,
                        ),
                      ),
                      const SizedBox(
                        height: 30,
                      ),

                      ...chapters.map(
                        (chapter) {
                          final words = widget
                              .allWords
                              .where(
                                (word) =>
                                    word.chapter ==
                                    chapter,
                              )
                              .toList();

                          final learned =
                              words.where(
                            (word) {
                              final p =
                                  progress[
                                      word.id];

                              return p !=
                                      null &&
                                  p.level >= 2;
                            },
                          ).length;

                          return Padding(
                            padding:
                                const EdgeInsets
                                    .only(
                              bottom: 10,
                            ),
                            child:
                                MaterialTile(
                              icon: Icons
                                  .menu_book_outlined,
                              title:
                                  'Kapitel $chapter',
                              subtitle:
                                  '${words.length} words • $learned learned',
                              onTap: () {
                                openChapter(
                                  chapter,
                                  words,
                                );
                              },
                            ),
                          );
                        },
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ============================================================
// STUDY OPTIONS
// ============================================================

class StudyOptionsPage
    extends StatefulWidget {
  final String title;
  final List<Word> words;
  final Map<String, WordProgress> progress;

  const StudyOptionsPage({
    super.key,
    required this.title,
    required this.words,
    required this.progress,
  });

  @override
  State<StudyOptionsPage> createState() =>
      _StudyOptionsPageState();
}

class _StudyOptionsPageState
    extends State<StudyOptionsPage> {
  late Map<String, WordProgress> progress;

  @override
  void initState() {
    super.initState();

    progress =
        Map<String, WordProgress>.from(
      widget.progress,
    );
  }

  int get newCount {
    return widget.words.where((word) {
      final p = progress[word.id];

      return p == null || p.level == 0;
    }).length;
  }

  int get learningCount {
    return widget.words.where((word) {
      return progress[word.id]?.level == 1;
    }).length;
  }

  int get dueCount {
    return widget.words.where((word) {
      final p = progress[word.id];

      return p != null &&
          p.level >= 2 &&
          isProgressDue(p);
    }).length;
  }

  int get learnedCount {
    return widget.words.where((word) {
      final p = progress[word.id];

      return p != null && p.level >= 2;
    }).length;
  }

  int get availableCount {
    return newCount +
        learningCount +
        dueCount;
  }

  Future<void> refreshProgress() async {
    final loaded =
        await loadProgress(widget.words);

    if (!mounted) return;

    setState(() {
      for (final word in widget.words) {
        progress.remove(word.id);
      }

      progress.addAll(loaded);
    });
  }

  Future<void> startSession(
    int? size,
  ) async {
    final session = buildStudySession(
      sourceWords: widget.words,
      progress: progress,
      sessionSize: size,
    );

    if (session.isEmpty) {
      if (!mounted) return;

      ScaffoldMessenger.of(context)
          .showSnackBar(
        const SnackBar(
          content: Text(
            'Nothing is due right now. Great job!',
          ),
        ),
      );

      return;
    }

    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) =>
            FlashcardPage(
          words: session,
          title: widget.title,
          progress: progress,
        ),
      ),
    );

    await refreshProgress();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.title),
      ),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding:
                const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints:
                  const BoxConstraints(
                maxWidth: 550,
              ),
              child: Column(
                children: [
                  const Icon(
                    Icons.school_outlined,
                    size: 65,
                  ),

                  const SizedBox(height: 15),

                  Text(
                    widget.title,
                    style: const TextStyle(
                      fontSize: 30,
                      fontWeight:
                          FontWeight.bold,
                    ),
                  ),

                  const SizedBox(height: 8),

                  Text(
                    '${widget.words.length} words',
                    style: const TextStyle(
                      color: Colors.grey,
                    ),
                  ),

                  const SizedBox(height: 30),

                  const SectionTitle(
                    title: 'PROGRESS',
                  ),

                  const SizedBox(height: 12),

                  ProgressSummaryTile(
                    icon:
                        Icons.fiber_new_outlined,
                    title: 'New',
                    count: newCount,
                  ),

                  ProgressSummaryTile(
                    icon: Icons.school_outlined,
                    title: 'Learning',
                    count: learningCount,
                  ),

                  ProgressSummaryTile(
                    icon:
                        Icons.schedule_outlined,
                    title: 'Due',
                    count: dueCount,
                  ),

                  ProgressSummaryTile(
                    icon: Icons
                        .check_circle_outline,
                    title: 'Learned',
                    count: learnedCount,
                  ),

                  const SizedBox(height: 35),

                  const SectionTitle(
                    title: 'CHOOSE SESSION',
                  ),

                  const SizedBox(height: 12),

                  SessionTile(
                    icon: Icons.bolt,
                    title: 'Quick Session',
                    subtitle: '10 words',
                    onTap: () {
                      startSession(10);
                    },
                  ),

                  const SizedBox(height: 10),

                  SessionTile(
                    icon: Icons.school_outlined,
                    title: 'Standard Session',
                    subtitle:
                        '20 words • Recommended',
                    recommended: true,
                    onTap: () {
                      startSession(20);
                    },
                  ),

                  const SizedBox(height: 10),

                  SessionTile(
                    icon: Icons
                        .local_fire_department_outlined,
                    title: 'Long Session',
                    subtitle: '50 words',
                    onTap: () {
                      startSession(50);
                    },
                  ),

                  const SizedBox(height: 10),

                  SessionTile(
                    icon: Icons.all_inclusive,
                    title: 'Study All',
                    subtitle:
                        '$availableCount words currently available',
                    onTap: () {
                      startSession(null);
                    },
                  ),

                  const SizedBox(height: 25),

                  const Text(
                    'Due reviews are shown first, followed by '
                    'Learning words and then new vocabulary.',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Colors.grey,
                      fontSize: 13,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// ============================================================
// FLASHCARDS
// ============================================================

class FlashcardPage extends StatefulWidget {
  final List<Word> words;
  final String title;
  final Map<String, WordProgress> progress;

  const FlashcardPage({
    super.key,
    required this.words,
    required this.title,
    required this.progress,
  });

  @override
  State<FlashcardPage> createState() =>
      _FlashcardPageState();
}

class _FlashcardPageState
    extends State<FlashcardPage> {
  int currentIndex = 0;

  bool showTranslation = false;

  int sessionKnown = 0;
  int sessionLearning = 0;

  late Map<String, WordProgress> progress;

  @override
  void initState() {
    super.initState();

    progress =
        Map<String, WordProgress>.from(
      widget.progress,
    );
  }

  Word get currentWord =>
      widget.words[currentIndex];

  Future<void> answerLearning() async {
    final newProgress =
        await markLearning(currentWord);

    progress[currentWord.id] =
        newProgress;

    sessionLearning++;

    await recordStudyAnswer(known: false);

    await nextWord();
  }

  Future<void> answerKnown() async {
    final newProgress = await markKnown(
      currentWord,
      progress[currentWord.id],
    );

    progress[currentWord.id] =
        newProgress;

    sessionKnown++;

    await recordStudyAnswer(known: true);

    await nextWord();
  }

  Future<void> nextWord() async {
    if (currentIndex <
        widget.words.length - 1) {
      if (!mounted) return;

      // Reset the flip widget completely when moving to a new word.
      // The key used below makes the new card start from the Swedish side
      // instead of inheriting the previous card's animation state.
      setState(() {
        currentIndex++;
        showTranslation = false;
      });

      return;
    }

    if (!mounted) return;

    await showDialog(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text(
            'Session complete! 🎉',
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                'You reviewed ${widget.words.length} words.',
              ),
              const SizedBox(height: 20),
              Row(
                mainAxisAlignment:
                    MainAxisAlignment
                        .spaceAround,
                children: [
                  Column(
                    children: [
                      Text(
                        '$sessionLearning',
                        style:
                            const TextStyle(
                          fontSize: 26,
                          fontWeight:
                              FontWeight.bold,
                        ),
                      ),
                      const Text('Learning'),
                    ],
                  ),
                  Column(
                    children: [
                      Text(
                        '$sessionKnown',
                        style:
                            const TextStyle(
                          fontSize: 26,
                          fontWeight:
                              FontWeight.bold,
                        ),
                      ),
                      const Text('I knew it'),
                    ],
                  ),
                ],
              ),
            ],
          ),
          actions: [
            FilledButton(
              onPressed: () {
                Navigator.pop(
                  dialogContext,
                );

                Navigator.pop(context);
              },
              child: const Text('DONE'),
            ),
          ],
        );
      },
    );
  }

  String currentStatusText() {
    final p = progress[currentWord.id];

    if (p == null || p.level == 0) {
      return 'NEW';
    }

    if (p.level == 1) {
      return 'LEARNING';
    }

    if (isProgressDue(p)) {
      return 'REVIEW';
    }

    return 'LEVEL ${p.level}';
  }

  @override
  Widget build(BuildContext context) {
    final cardProgress =
        (currentIndex + 1) / widget.words.length;

    final status = currentStatusText();

    return Scaffold(
      appBar: AppBar(
        title: Text(
          widget.title,
          style: const TextStyle(
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(
              maxWidth: 600,
            ),
            child: LayoutBuilder(
              builder: (context, constraints) {
                // Keep the card large on phones, but prevent it from
                // becoming excessively tall on desktop/tablet screens.
                final availableHeight = constraints.maxHeight;
                final targetCardHeight =
                    (availableHeight * 0.72).clamp(430.0, 650.0);

                return Padding(
                  padding: const EdgeInsets.fromLTRB(
                    20,
                    8,
                    20,
                    20,
                  ),
                  child: Column(
                    children: [
                      Row(
                        children: [
                          Text(
                            '${currentIndex + 1} / ${widget.words.length}',
                            style: const TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          const Spacer(),
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 11,
                              vertical: 6,
                            ),
                            decoration: BoxDecoration(
                              color: const Color(0xFFE3F1FA),
                              borderRadius:
                                  BorderRadius.circular(20),
                            ),
                            child: Text(
                              status,
                              style: const TextStyle(
                                color: Color(0xFF006AA7),
                                fontSize: 12,
                                fontWeight: FontWeight.w800,
                                letterSpacing: 0.5,
                              ),
                            ),
                          ),
                        ],
                      ),

                      const SizedBox(height: 10),

                      ClipRRect(
                        borderRadius: BorderRadius.circular(20),
                        child: LinearProgressIndicator(
                          value: cardProgress,
                          minHeight: 8,
                          backgroundColor:
                              const Color(0xFFDCEAF5),
                        ),
                      ),

                      const SizedBox(height: 18),

                      Expanded(
                        child: Center(
                          child: SizedBox(
                            height: targetCardHeight,
                            width: double.infinity,
                            child: GestureDetector(
                              onTap: () {
                                setState(() {
                                  showTranslation =
                                      !showTranslation;
                                });
                              },
                              child: TweenAnimationBuilder<double>(
                                key: ValueKey(currentWord.id),
                                tween: Tween<double>(
                                  begin: 0,
                                  end: showTranslation ? 1 : 0,
                                ),
                                duration:
                                    const Duration(milliseconds: 420),
                                curve: Curves.easeInOutCubic,
                                builder: (context, value, child) {
                                  final angle = value * pi;
                                  final showingBack = value >= 0.5;

                                  return Transform(
                                    alignment: Alignment.center,
                                    transform: Matrix4.identity()
                                      ..setEntry(3, 2, 0.0012)
                                      ..rotateY(angle),
                                    child: Transform(
                                      alignment: Alignment.center,
                                      transform: Matrix4.identity()
                                        ..rotateY(
                                          showingBack ? pi : 0,
                                        ),
                                      child: _buildFlashcardFace(
                                        showEnglish: showingBack,
                                      ),
                                    ),
                                  );
                                },
                              ),
                            ),
                          ),
                        ),
                      ),

                      const SizedBox(height: 16),

                      AnimatedSwitcher(
                        duration:
                            const Duration(milliseconds: 180),
                        child: showTranslation
                            ? Row(
                                key: const ValueKey(
                                  'answer-buttons',
                                ),
                                children: [
                                  Expanded(
                                    child: OutlinedButton.icon(
                                      onPressed: answerLearning,
                                      icon: const Icon(
                                        Icons.close_rounded,
                                      ),
                                      label: const Text(
                                        'LEARNING',
                                      ),
                                      style:
                                          OutlinedButton.styleFrom(
                                        minimumSize:
                                            const Size.fromHeight(
                                          58,
                                        ),
                                        shape:
                                            RoundedRectangleBorder(
                                          borderRadius:
                                              BorderRadius.circular(
                                            16,
                                          ),
                                        ),
                                      ),
                                    ),
                                  ),
                                  const SizedBox(width: 12),
                                  Expanded(
                                    child: FilledButton.icon(
                                      onPressed: answerKnown,
                                      icon: const Icon(
                                        Icons.check_rounded,
                                      ),
                                      label: const Text(
                                        'I KNOW',
                                      ),
                                      style:
                                          FilledButton.styleFrom(
                                        minimumSize:
                                            const Size.fromHeight(
                                          58,
                                        ),
                                        backgroundColor:
                                            const Color(
                                          0xFF006AA7,
                                        ),
                                        shape:
                                            RoundedRectangleBorder(
                                          borderRadius:
                                              BorderRadius.circular(
                                            16,
                                          ),
                                        ),
                                      ),
                                    ),
                                  ),
                                ],
                              )
                            : const SizedBox(
                                key: ValueKey(
                                  'answer-placeholder',
                                ),
                                height: 58,
                              ),
                      ),
                    ],
                  ),
                );
              },
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildFlashcardFace({
    required bool showEnglish,
  }) {
    return Card(
      elevation: 2,
      shadowColor: Colors.black.withValues(
        alpha: 0.12,
      ),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(24),
        side: BorderSide(
          color: Colors.grey.shade200,
        ),
      ),
      child: SizedBox.expand(
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 6,
                ),
                decoration: BoxDecoration(
                  color: showEnglish
                      ? const Color(0xFFFFF3BF)
                      : const Color(0xFFE3F1FA),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  showEnglish ? 'ENGLISH' : 'SVENSKA',
                  style: TextStyle(
                    color: showEnglish
                        ? const Color(0xFF7A5B00)
                        : const Color(0xFF006AA7),
                    fontSize: 12,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 0.8,
                  ),
                ),
              ),

              const SizedBox(height: 28),

              if (!showEnglish) ...[
                Flexible(
                  child: FittedBox(
                    fit: BoxFit.scaleDown,
                    child: Text(
                      currentWord.swedish,
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                        fontSize: 46,
                        fontWeight: FontWeight.w800,
                        letterSpacing: -0.8,
                      ),
                    ),
                  ),
                ),
                if (currentWord.forms.isNotEmpty) ...[
                  const SizedBox(height: 14),
                  Text(
                    currentWord.forms,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 19,
                      color: Colors.grey.shade600,
                    ),
                  ),
                ],
              ] else ...[
                Flexible(
                  child: FittedBox(
                    fit: BoxFit.scaleDown,
                    child: Text(
                      currentWord.english,
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                        fontSize: 40,
                        fontWeight: FontWeight.w800,
                        letterSpacing: -0.5,
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 24),
                Container(
                  width: 46,
                  height: 3,
                  decoration: BoxDecoration(
                    color: const Color(0xFFFECC02),
                    borderRadius: BorderRadius.circular(10),
                  ),
                ),
                const SizedBox(height: 22),
                Text(
                  currentWord.swedish,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    fontSize: 23,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                if (currentWord.forms.isNotEmpty) ...[
                  const SizedBox(height: 7),
                  Text(
                    currentWord.forms,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 17,
                      color: Colors.grey.shade600,
                    ),
                  ),
                ],
              ],

              const SizedBox(height: 30),

              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    Icons.touch_app_outlined,
                    size: 18,
                    color: Colors.grey.shade500,
                  ),
                  const SizedBox(width: 7),
                  Text(
                    showEnglish
                        ? 'Tap card to flip back'
                        : 'Tap to reveal',
                    style: TextStyle(
                      color: Colors.grey.shade600,
                      fontSize: 14,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ============================================================
// UI COMPONENTS
// ============================================================

class SectionTitle extends StatelessWidget {
  final String title;

  const SectionTitle({
    super.key,
    required this.title,
  });

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Text(
        title,
        style: const TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.bold,
          color: Colors.grey,
        ),
      ),
    );
  }
}

class StatisticsCard extends StatelessWidget {
  final IconData icon;
  final int value;
  final String label;

  const StatisticsCard({
    super.key,
    required this.icon,
    required this.value,
    required this.label,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
        side: BorderSide(color: Colors.grey.shade200),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: 8,
          vertical: 16,
        ),
        child: Column(
          children: [
            Icon(
              icon,
              color: const Color(0xFF006AA7),
              size: 25,
            ),
            const SizedBox(height: 8),
            Text(
              value.toString(),
              style: const TextStyle(
                fontSize: 23,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 2),
            Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Colors.grey.shade600,
                fontSize: 11,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class StatisticsRow extends StatelessWidget {
  final String label;
  final int value;

  const StatisticsRow({
    super.key,
    required this.label,
    required this.value,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Text(
            label,
            style: const TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
        Text(
          value.toString(),
          style: const TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.w800,
          ),
        ),
      ],
    );
  }
}

class ProgressStatCard extends StatelessWidget {
  final IconData icon;
  final String title;
  final int count;

  const ProgressStatCard({
    super.key,
    required this.icon,
    required this.title,
    required this.count,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
        side: BorderSide(
          color: Colors.grey.shade200,
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Container(
              width: 42,
              height: 42,
              decoration: BoxDecoration(
                color: const Color(0xFFE3F1FA),
                borderRadius: BorderRadius.circular(13),
              ),
              child: Icon(
                icon,
                color: const Color(0xFF006AA7),
                size: 23,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment:
                    CrossAxisAlignment.start,
                children: [
                  Text(
                    count.toString(),
                    style: const TextStyle(
                      fontSize: 21,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const SizedBox(height: 1),
                  Text(
                    title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: Colors.grey.shade600,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class ProgressSummaryTile
    extends StatelessWidget {
  final IconData icon;
  final String title;
  final int count;

  const ProgressSummaryTile({
    super.key,
    required this.icon,
    required this.title,
    required this.count,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      margin:
          const EdgeInsets.only(bottom: 10),
      child: ListTile(
        leading: Icon(
          icon,
          size: 30,
        ),
        title: Text(
          title,
          style: const TextStyle(
            fontWeight: FontWeight.w600,
          ),
        ),
        trailing: Text(
          count.toString(),
          style: const TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.bold,
          ),
        ),
      ),
    );
  }
}

class MaterialTile extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  const MaterialTile({
    super.key,
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.zero,
      child: ListTile(
        onTap: onTap,
        leading: Icon(
          icon,
          size: 30,
        ),
        title: Text(
          title,
          style: const TextStyle(
            fontWeight: FontWeight.w600,
          ),
        ),
        subtitle: Text(subtitle),
        trailing:
            const Icon(Icons.chevron_right),
      ),
    );
  }
}

class SessionTile extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;
  final bool recommended;

  const SessionTile({
    super.key,
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
    this.recommended = false,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.zero,
      child: ListTile(
        onTap: onTap,
        leading: Icon(
          icon,
          size: 30,
        ),
        title: Row(
          children: [
            Flexible(
              child: Text(
                title,
                style: const TextStyle(
                  fontWeight:
                      FontWeight.w600,
                ),
              ),
            ),
            if (recommended) ...[
              const SizedBox(width: 8),
              Container(
                padding:
                    const EdgeInsets.symmetric(
                  horizontal: 8,
                  vertical: 3,
                ),
                decoration: BoxDecoration(
                  color: Theme.of(context)
                      .colorScheme
                      .primaryContainer,
                  borderRadius:
                      BorderRadius.circular(20),
                ),
                child: const Text(
                  'RECOMMENDED',
                  style: TextStyle(
                    fontSize: 9,
                    fontWeight:
                        FontWeight.bold,
                  ),
                ),
              ),
            ],
          ],
        ),
        subtitle: Text(subtitle),
        trailing:
            const Icon(Icons.chevron_right),
      ),
    );
  }
}

class DailyReviewTile extends StatelessWidget {
  final int dueCount;
  final VoidCallback onTap;

  const DailyReviewTile({
    super.key,
    required this.dueCount,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.zero,
      child: InkWell(
        onTap: onTap,
        borderRadius:
            BorderRadius.circular(12),
        child: Padding(
          padding:
              const EdgeInsets.all(20),
          child: Row(
            children: [
              Container(
                width: 55,
                height: 55,
                decoration: BoxDecoration(
                  color: Theme.of(context)
                      .colorScheme
                      .primaryContainer,
                  borderRadius:
                      BorderRadius.circular(16),
                ),
                child: Icon(
                  Icons.refresh,
                  color: Theme.of(context)
                      .colorScheme
                      .onPrimaryContainer,
                ),
              ),

              const SizedBox(width: 18),

              Expanded(
                child: Column(
                  crossAxisAlignment:
                      CrossAxisAlignment
                          .start,
                  children: [
                    Text(
                      '$dueCount ${dueCount == 1 ? 'word' : 'words'} due',
                      style:
                          const TextStyle(
                        fontSize: 18,
                        fontWeight:
                            FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 4),
                    const Text(
                      'Ready for today\'s review',
                      style: TextStyle(
                        color: Colors.grey,
                      ),
                    ),
                  ],
                ),
              ),

              const Icon(
                Icons.chevron_right,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class DailyCompleteTile
    extends StatelessWidget {
  const DailyCompleteTile({
    super.key,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding:
            const EdgeInsets.all(20),
        child: Row(
          children: [
            Container(
              width: 55,
              height: 55,
              decoration: BoxDecoration(
                color: Theme.of(context)
                    .colorScheme
                    .secondaryContainer,
                borderRadius:
                    BorderRadius.circular(16),
              ),
              child: Icon(
                Icons.check,
                color: Theme.of(context)
                    .colorScheme
                    .onSecondaryContainer,
              ),
            ),

            const SizedBox(width: 18),

            const Expanded(
              child: Column(
                crossAxisAlignment:
                    CrossAxisAlignment
                        .start,
                children: [
                  Text(
                    'You\'re done for today!',
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight:
                          FontWeight.bold,
                    ),
                  ),
                  SizedBox(height: 4),
                  Text(
                    'No reviews are due.',
                    style: TextStyle(
                      color: Colors.grey,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}